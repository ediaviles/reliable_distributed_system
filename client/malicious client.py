import os, argparse
import time
import socket
import itertools
import sys
import threading


utils_path = os.path.join(os.path.dirname(__file__), '..')
sys.path.append(utils_path)
import utils
from CustomLog import *

class Client(object):
    def __init__(self, client_id, mode, timeout=0.1, local=False):
        if mode != "passive" and mode != "active":
            raise Exception("Invalid mode")
        self.client_id = client_id
        self.state = 100
        self.timeout = timeout
        self.mode = mode
        self.local = local
        self.passive_index = 0
        self.server_ids = list(utils.servers.keys())

    def __repr__(self):
        return f"C{self.client_id}"

    def send_message(self):
        self.update_client_state()
        available_servers = dict()
        server_list = range(len(self.server_ids))
        if self.mode == "passive":
            server_list = itertools.chain(server_list[self.passive_index:], server_list[:self.passive_index])

        # For active mode, try all servers
        # For passive mode, try passive_index, then passive_index+1, until we find a server that is available
        max_retry = 5
        for s in server_list:
            server = self.server_ids[s]
            try:
                for _ in range(max_retry):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.settimeout(2)
                    server_ip = utils.servers[server].ip
                    if self.local:
                        server_ip = "127.0.0.1"
                    sock.connect((
                        server_ip,
                        utils.servers[server].port.general_port
                    ))
                    available_servers[server] = sock
                    break
                if self.mode == "passive":
                    break
            except:
                if self.mode == "passive":
                    logger.error(f"S{server}: Connection declined. Trying next server.")
                    self.passive_index = (self.passive_index + 1) % len(utils.servers.keys())

        # Try to connect one more time
        if self.mode == "active":
            for s in server_list:
                server = self.server_ids[s]
                if server not in available_servers:
                    try:
                        for _ in range(max_retry):
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            sock.settimeout(2)
                            server_ip = utils.servers[server].ip
                            if self.local:
                                server_ip = "127.0.0.1"
                            sock.connect((
                                server_ip,
                                utils.servers[server].port.general_port
                            ))
                            available_servers[server] = sock
                            break
                        if self.mode == "passive":
                            break
                    except:
                        logger.error(f"S{server}: Connection declined")

        received_states = set()
        for server in available_servers:
            try:
                start = utils.now()
                start = start.second + start.microsecond * 10**-6
                m = utils.Message(source=self, destination=f"S{server}", message_num=self.state, message_type="request", state=start)
                logger.send(f"Sent {m}") # type: ignore
                available_servers[server].settimeout(20)
                available_servers[server].send(str(m).encode("ascii"))
                reply = available_servers[server].recv(1024)
                reply_message = utils.Message(ascii_string=reply.decode('ascii'))
                if reply_message.source is not None:
                    logger.state(f"Received {reply_message}") # type: ignore
                    # Duplicate detection
                    if reply_message.message_state not in received_states:
                        received_states.add(reply_message.message_state)
                    else:
                        logger.info(f"request_num {self.state}: Disregared duplicate reply from S{server}")
                elif self.mode == "passive":
                    logger.error(f"S{server}: Response empty. Trying next server.")
                    self.passive_index = (self.passive_index + 1) % len(utils.servers.keys())
            except Exception as err:
                logger.error(f"S{server}: No reply: {err}")
                if self.mode == "passive":
                    logger.error(f"S{server}: Response failed. Trying next server.")
                    self.passive_index = (self.passive_index + 1) % len(utils.servers.keys())

    def update_client_state(self):
        self.state += 1

    def _malicious_send_message(self):
        while (True):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_ip = utils.servers[1].ip
            if self.local:
                server_ip = "127.0.0.1"
            sock.connect((
                server_ip,
                utils.servers[1].port.general_port
            ))
            start = utils.now()
            m = utils.Message(source=self, destination=f"S1", message_num=self.state, message_type="request", state=start)
            sock.send(str(m).encode("ascii"))


def main(args):
    # establish connection
    c = Client(client_id=args.client_id, mode=args.mode, local=args.local)
    
    malicious_thread_1 = threading.Thread(target=c._malicious_send_message)
    malicious_thread_2 = threading.Thread(target=c._malicious_send_message)
    malicious_thread_3 = threading.Thread(target=c._malicious_send_message)
    malicious_thread_4 = threading.Thread(target=c._malicious_send_message)
    malicious_thread_5 = threading.Thread(target=c._malicious_send_message)


    malicious_thread_1.start()
    malicious_thread_2.start()
    malicious_thread_3.start()
    malicious_thread_4.start()
    malicious_thread_5.start()


    malicious_thread_1.join()
    malicious_thread_2.join()
    malicious_thread_3.join()
    malicious_thread_4.join()
    malicious_thread_5.join()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='18-749 Client')
    parser.add_argument("-n", "--client-id",
                        choices=range(1, 3+1),
                        type=int, required=True)
    parser.add_argument("-l", "--local",
          help="Connect to servers locally",
          action="store_true")
    parser.add_argument("-m", "--mode",
          help="Passive or active server mode",
          choices=["passive", "active"],
          required=True)
    parser.add_argument("-f", "--ping-frequency",
          help="The number of times per second the client is sending a request",
          type=float, required=False, default=2)

    args = parser.parse_args()
    main(args)
