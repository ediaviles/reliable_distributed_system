import socket
import os, sys, argparse
import datetime


utils_path = os.path.join(os.path.dirname(__file__), '..')
sys.path.append(utils_path)
import utils
from CustomLog import *

class RM():
    def __init__(self, mode):
        self.ip = utils.rm.ip
        self.port = utils.rm.port
        self.mode = mode
        self.member_count = 0
        self.membership = None
        self.primary=None

        self.min_time = None
        self.max_time = None
        self.total_time = 0
        self.response_count = 0
        self.last_db_write = None

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(2)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(socket.SOMAXCONN)

        logger.debug(f'RM is now listening on port {self.port}!')
        logger.debug(self)

    def __repr__(self):
        if(self.membership == None or self.member_count == 0):
            return f"RM: 0 members"
        return f"RM: {self.member_count} members: {[x for x in list(self.membership)]}"

    def register_GFD(self):
        try:
            client, addr = self.sock.accept()
        except Exception:
            client = None

        if client is not None:
            data = client.recv(4096).decode("ascii")
            logger.receive(f"Received {data}")
            message = utils.Message(ascii_string=data)

            if message.destination == "RM" and message.source == "GFD" and message.message_type == "register":
                logger.heartbeat(f"Received connection request from {message.source}")
                response = utils.Message(source="RM", destination="GFD", message_num=message.message_num, message_type="reply", state=True)
                logger.info(self)
                end = utils.now()
                new_time = end - datetime.datetime.strptime(message.message_state, '%Y-%m-%d %H:%M:%S.%f') 
                new_time = new_time.seconds + new_time.microseconds * 10 ** -6
                self.update_time_values(new_time)
                client.send(str(response).encode("ascii"))
                self.membership = set()
            else:
                logger.error(f"Unintended Recipient. RM cannot connect with {message.source}")

    def reset_values(self):
        self.max_time, self.min_time = None, None


    def update_time_values(self, new_time):
        if self.min_time != None and self.max_time != None:
            self.min_time, self.max_time = min(self.min_time, new_time), max(self.max_time, new_time)
        else:
            self.min_time, self.max_time = new_time, new_time
        self.total_time += new_time
        self.response_count += 1
    
    def connect_to_servers(self,server_id):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((utils.servers[server_id].ip, utils.servers[server_id].port.general_port))
                sock.settimeout(2)
                request = utils.Message(source="RM", destination=f"S{server_id}", message_num=0, message_type=f"primary {self.primary}")
                logger.send(f"Sending {request}")
                sock.send(str(request).encode("ascii"))
                response = sock.recv(1024)
                logger.receive(f"Received {response}")
        except Exception:
            logger.error(f"Cannot send to S{server_id}")

    def handle_members(self):
        try:
            client, addr = self.sock.accept()
        except Exception:
            client = None

        if client is not None:
            data = client.recv(4096).decode("ascii")
            logger.receive(f"Received {data}")
            message = utils.Message(ascii_string=data)

            if(message.destination == "RM" and message.source == "GFD" and
              ("Add S" in message.message_type or "Remove S" in message.message_type)):
                logger.info(f"Received connection request from GFD to {message.message_type.lower()}")
                server_name = message.message_type.split(" ")[-1]
                response = utils.Message(source="RM", destination="GFD", message_num=message.message_num, message_type="reply", state=False)
                end = utils.now()
                new_time = end - datetime.datetime.strptime(message.message_state, '%Y-%m-%d %H:%M:%S.%f')
                new_time = new_time.seconds + new_time.microseconds * 10 ** -6
                self.update_time_values(new_time)
                if(message.message_type.startswith("Add") and server_name not in self.membership):
                    response = utils.Message(source="GFD", destination="RM", message_num=message.message_num, message_type="reply", state=True)
                    self.membership.add(server_name)
                    if(self.mode == "passive"):
                        if(self.member_count==0):
                            self.primary=server_name
                        self.connect_to_servers(int(server_name[1:]))

                elif(message.message_type.startswith("Remove") and server_name in self.membership):
                    response = utils.Message(source="GFD", destination="RM", message_num=message.message_num, message_type="reply", state=True)
                    self.membership.remove(server_name)

                end = utils.now()
                new_time = end - datetime.datetime.strptime(message.message_state, '%Y-%m-%d %H:%M:%S.%f')
                new_time = new_time.seconds + new_time.microseconds * 10 ** -6
                self.update_time_values(new_time)
                logger.send(f"Sending {response}")
                client.send(str(response).encode("ascii"))

                if(self.mode == "passive" and self.primary==server_name and message.message_type.startswith("Remove")):
                    logger.debug(f"Primary before change {self.primary}")
                    if len(list(self.membership)) == 0:
                        self.primary = None
                    else:
                        self.primary=sorted(list(self.membership))[0]
                    logger.debug(f"Primary after change: {self.primary}")
                    for member in list(self.membership):
                        self.connect_to_servers(int(member[1:]))


                self.member_count = len(self.membership)
                logger.info(self)
            else:
                if(message.source!="GFD"): logger.error(f"RM cannot connect with {message.source}")
                else: logger.error(f"Cannot perform {message.message_type}. Please check.")

    def monitor_system(self):
        while(True):
            if(self.membership == None):
                self.register_GFD()
            else:
                self.handle_members()
            self.write_to_db()

    def write_to_db(self):
        if self.last_db_write == None or utils.now() - self.last_db_write >= datetime.timedelta(seconds=10):
            collection_gfd_to_rm = utils.db["gfd-rm"]
            component_id = 1
            count = self.response_count if self.response_count > 0 else 1
            data = {
                "performance" : [self.max_time, self.min_time, self.total_time / count]
            }
            utils.check_and_update_collection_data(collection_gfd_to_rm, component_id, data)
            self.last_db_write = utils.now()
            self.reset_values()



def main():
    parser = argparse.ArgumentParser(prog='18-749 Server')
    parser.add_argument("-m", "--mode",
                        help="Passive or active server mode",
                        choices=["passive", "active"], required=True)
    args = parser.parse_args()
    rm = RM(args.mode)
    rm.monitor_system()

if __name__ == '__main__':
    main()
