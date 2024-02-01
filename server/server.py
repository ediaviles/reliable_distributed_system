import json
import socket, signal
import os, sys, argparse
import datetime
import threading

utils_path = os.path.join(os.path.dirname(__file__), '..')
sys.path.append(utils_path)
import utils
from CustomLog import *

parser = argparse.ArgumentParser(prog='18-749 Server')
parser.add_argument("-n", "--server-id",
                    choices=range(1, 4),
                    type=int, required=True)
parser.add_argument("-t", "--lfd-timeout",
                    help="Time in seconds that server should run without hearing from LFD",
                    type=float, required=False, default=100)
parser.add_argument("-m", "--mode",
                    help="Passive or active server mode",
                    choices=["passive", "active"], required=True)
parser.add_argument("-f", "--checkpoint-frequency",
          help="Checkpointing frequency between servers for passive replication",
          type=float, required=False, default=10)

class Server():
    def __init__(self, index, mode, checkpoint_freq):
        if mode != "passive" and mode != "active":
            raise Exception("Invalid mode")
        self.index = index
        self.mode = mode
        self.primary = False
        self.checkpoint_freq = checkpoint_freq
        self.checkpoint_count = 1
        self.lastCheckpointTime = None
        self.name = f"S{index}"
        self.lfd = f"LFD{index}"
        self.port = utils.servers[index].port.general_port
        # Message counts from each of the clients
        self.my_state = {"C1": 0, "C2": 0, "C3": 0}
        self.i_am_ready = False
        if self.mode == "passive" and self.primary == True:
            self.i_am_ready = True
        self.last_heard_from_lfd = utils.now()
        self.is_running = True

        self.min_time = None
        self.max_time = None
        self.response_count = 0
        self.total_time = 0
        self.last_db_write = None

        self.min_lfd_time = None
        self.max_lfd_time = None
        self.lfd_response_count = 0
        self.lfd_total_time = 0

        self.lfd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lfd_sock.settimeout(1)
        self.lfd_sock.bind(('', utils.servers[index].port.lfd_port))
        self.lfd_sock.listen(socket.SOMAXCONN)

        self.sock = None
    
    def __repr__(self):
        return self.name
    
    def handle_lfd_heartbeat(self):
        try:
            lfd, addr = self.lfd_sock.accept()
        except Exception:
            lfd = None
        if lfd is not None:
            data = lfd.recv(2048)
            data = data.decode("ascii")
            logger.receive(f"Received {data}")
            message = utils.Message(ascii_string=data)
            if message.destination == self.name and message.source == self.lfd:
                self.last_heard_from_lfd = utils.now()
                end = self.last_heard_from_lfd
                start = datetime.datetime.strptime(message.message_state, '%Y-%m-%d %H:%M:%S.%f')
                new_time = end - start
                new_time = new_time.seconds + new_time.microseconds*10**-6
                self.update_lfd_time_values(new_time)
                logger.heartbeat(f"Received heartbeat message from {message.source}")
                response = utils.Message(source=self, destination=self.lfd, message_num=message.message_num, message_type="reply")
                logger.send(f"Sending {response}")
                lfd.send(str(response).encode("ascii"))

    def update_time_values(self, new_time):
        if self.min_time != None and self.max_time != None:
            self.min_time, self.max_time = min(self.min_time, new_time), max(self.max_time, new_time)
        else:
            self.min_time, self.max_time = new_time, new_time
        self.total_time += new_time
        self.response_count += 1

    def update_lfd_time_values(self, new_time):
        if self.min_lfd_time != None and self.max_lfd_time != None:
            self.min_lfd_time, self.max_lfd_time = min(self.min_lfd_time, new_time), max(self.max_lfd_time, new_time)
        else:
            self.min_lfd_time, self.max_lfd_time = new_time, new_time
        self.lfd_total_time += new_time
        self.lfd_response_count += 1

    def handle_requests(self):
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.settimeout(2)
            self.sock.bind(('', self.port))
            self.sock.listen(socket.SOMAXCONN)
            logger.debug(f'Server is now listening on port {self.port}!')
            logger.state(f"my_state = {self.my_state}")

        try:
            client, addr = self.sock.accept()
        except Exception:
            client = None
        
        if client is not None:
            data = client.recv(2048)
            data = data.decode("ascii")
            logger.receive(f"Received {data}")
            message = utils.Message(ascii_string=data)
            if message.destination == self.name:
                if message.source in self.my_state.keys(): # Client Message
                    if self.i_am_ready and (self.mode == "active" or (self.mode == "passive" and self.primary == True)):
                        logger.info(f"my_state = {self.my_state} before processing {data}")
                        self.my_state[message.source] += 1
                        logger.state(f"my_state = {self.my_state} after processing {data}")
                        start = datetime.datetime.strptime(message.message_state, '%Y-%m-%d %H:%M:%S.%f') # float value
                        end = utils.now()
                        response_time = end - start
                        response_time = response_time.seconds + response_time.microseconds * 10 ** -6
                        self.update_time_values(response_time)
                        # Only send state associated with specific client (C1 only sees state[C1] and so on)
                        response = utils.Message(source=self, destination=message.source, message_num=message.message_num, message_type="reply", state=self.my_state[message.source])
                        logger.send(f"Sending {response}")
                        client.send(str(response).encode("ascii"))
                elif message.source.startswith("S"): # Checkpoint messages
                    if message.message_type == "checkpoint": # Receive Checkpoint
                        #  and (not self.i_am_ready or (self.mode == "passive" and message.source == f"S{self.primary}"))
                        self.accept_checkpoint(client, data, message)
                        if self.mode == "active":
                            self.i_am_ready = True
                            logger.info(f"i_am_ready = {self.i_am_ready}")
                            logger.state(f"my_state = {self.my_state}")
                    elif self.i_am_ready and message.message_type == "request": # Send Checkpoint
                        self.send_checkpoint(client, message.source[1], message.message_num)
                elif message.source == "RM":
                    logger.debug(f"Primary change to {message.message_type}")
                    if message.message_type == f"primary S{self.index}":
                        self.primary = True
                        self.i_am_ready = True
                        logger.debug(f"S{self.index} is the primary")
                    response = utils.Message(source=self, destination=message.source, message_num=message.message_num, message_type="acknowledge")
                    logger.send(f"Sending {response}")
                    client.send(str(response).encode("ascii"))
            else:
                logger.error(f"Unintended Recipient")
        
    def checkpoint_state(self):
        if(self.lastCheckpointTime == None or
           utils.now() - self.lastCheckpointTime >= datetime.timedelta(seconds=self.checkpoint_freq)):
            self.lastCheckpointTime = utils.now()
            self.checkpoint_count += 1
            for server in utils.servers:
                if(server != self.index):
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                            sock.settimeout(1)
                            sock.connect((utils.servers[server].ip, utils.servers[server].port.general_port))
                            self.send_checkpoint(sock, server, self.checkpoint_count)
                    except:
                        logger.error(f"Error with sending checkpoint to S{server}")
    
    def request_checkpoint(self):
        available_servers = dict()
        self.checkpoint_count += 1
        for server in utils.servers.keys():
            try:
                if server != self.index:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.settimeout(5)
                    server_ip = utils.servers[server].ip
                    sock.connect((
                        server_ip,
                        utils.servers[server].port.general_port
                    ))
                    available_servers[server] = sock
            except:
                logger.error(f"S{server}: Connection declined")
        
        for server in available_servers:
            try:
                m = utils.Message(source=self, destination=f"S{server}", message_num=self.checkpoint_count, message_type="request")
                logger.send(f"Sent {m}")
                available_servers[server].send(str(m).encode("ascii"))
                data = available_servers[server].recv(2048)
                data = data.decode("ascii")
                logger.receive(f"Received {data}")
                message = utils.Message(ascii_string=data)
                if message.destination == self.name and message.source.startswith("S") and message.message_type == "checkpoint":
                    print("Received checkpoint")
                    self.accept_checkpoint(available_servers[server], data, message)
                    if self.mode == "active":
                        self.i_am_ready = True
                        logger.info(f"i_am_ready = {self.i_am_ready}")
                        logger.state(f"my_state = {self.my_state}")
            except:
                logger.error(f"S{server}: No reply")
        if len(available_servers.keys()) == 0:
            self.i_am_ready = True
        logger.info(f"i_am_ready = {self.i_am_ready}")
        logger.state(f"my_state = {self.my_state}")

    def send_checkpoint(self, client, server, message_num):
        try:
            request = utils.Message(source=f"S{self.index}", destination=f"S{server}", message_num=message_num, message_type="checkpoint", state=(self.my_state, message_num))
            logger.send(f"Attempting Checkpoint {request}")
            client.send(str(request).encode("ascii"))
            response = client.recv(2048)
        except Exception:
            response = None

        if not response:
            logger.error(f"Error with server S{server}. S{server} is down!")
        else:
            received_message = response.decode('ascii')
            logger.receive(f"Checkpoint Success {request}")
            received_headers = utils.Message(ascii_string = received_message)

    def accept_checkpoint(self, client, data, message):
        logger.info(f"my_state = {self.my_state} before processing {data}")
        new_state = message.message_state.replace("'", "\"")
        if not self.i_am_ready:
            self.my_state = json.loads(new_state)
            self.i_am_ready = True
        self.checkpoint_count = int(message.checkpoint_count)
        logger.state(f"my_state = {self.my_state} after processing {data}")
        response = utils.Message(source=self, destination=message.source, message_num=message.message_num, message_type="reply", state=self.my_state)
        logger.send(f"Sending {response}")
        client.send(str(response).encode("ascii"))
   
    def _handle_lfd_heartbeat(self):
        while (self.is_running):
            last_heard_from_time = server.last_heard_from_lfd
            current_time = utils.now()
            delta = current_time - last_heard_from_time
            if (delta.total_seconds() > args.lfd_timeout):
                logger.critical(f"No message from LFD in {delta.total_seconds()} seconds. Server shutting down now.")
                try:
                    self.lfd_sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass

                self.lfd_sock.close()
                self.sock.close()
                self.is_running = False
                exit()
            self.handle_lfd_heartbeat()
    
    def write_to_db(self):
        if self.last_db_write == None or utils.now() - self.last_db_write >= datetime.timedelta(seconds=10):
            collection_client_to_server = utils.db["client-server"]
            collection_lfd_to_server = utils.db["lfd-server"]
            server_id = self.index
            count = self.response_count if self.response_count > 0 else 1
            lfd_count = self.lfd_response_count if self.lfd_response_count > 0 else 1
            data = {
                "performance" : [self.max_time, self.min_time, self.total_time / count]
            }
            data_lfd = {
                "performance": [self.max_lfd_time, self.min_lfd_time, self.lfd_total_time / lfd_count]
            }
            utils.check_and_update_collection_data(collection_client_to_server, server_id, data)
            utils.check_and_update_collection_data(collection_lfd_to_server, server_id, data_lfd)
            self.last_db_write = utils.now()
            self.reset_values()

    def reset_values(self):
        self.max_time, self.min_time = None, None
        self.max_lfd_time, self.min_lfd_time = None, None

    def _handle_requests(self):
        while (self.is_running):
            if self.mode == "active":
                if not self.i_am_ready:
                    self.request_checkpoint()
                else:
                    self.handle_requests()
                self.write_to_db()
            elif self.mode == "passive":
                if self.primary == True:
                    self.checkpoint_state()
                self.handle_requests()

    def _handle_db_write(self):
        while (self.is_running):
            self.write_to_db()



def sigint_wrapper(server, originalSigintHandler):
    def sigint_handler(signum, frame):
        server.sock.shutdown(socket.SHUT_RDWR)
        server.sock.close()
        server.is_running = False

        signame = signal.Signals(signum).name
        # print(f"\nsigname({signame})\nsignum({signum})\nframe:\n{frame}")
        print(f"\nsigname({signame})\nsignum({signum})")
        # match originalSigintHandler:
        #     case signal.SIG_IGN:
        #         pass
        #     case signal.SIG_DFL:
        #         pass
        #     case None:
        #         pass
        #     case _:
        #         originalSigintHandler(signum, frame)
        raise OSError("Catching Interrupt. Socket resources were freed.")
    return sigint_handler

if __name__ == '__main__':
    args = parser.parse_args()
    server = Server(args.server_id, args.mode, args.checkpoint_frequency)

    lfd_heartbeating_thread = threading.Thread(target=server._handle_lfd_heartbeat)
    request_handling_thread = threading.Thread(target=server._handle_requests)
    db_handling_thread = threading.Thread(target=server._handle_db_write)

    lfd_heartbeating_thread.start()
    request_handling_thread.start()
    db_handling_thread.start()

    lfd_heartbeating_thread.join()
    request_handling_thread.join()
    db_handling_thread.join()
