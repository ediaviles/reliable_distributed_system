import datetime
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection


def now():
    return datetime.datetime.now()

def timestamp():
    return now().isoformat()

class ServerEndpoint(object):
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

class ServerPorts(object):
    def __init__(self, lfd_port, general_port):
        self.lfd_port = lfd_port
        self.general_port = general_port

class Message(object):
    def __init__(self, source=None, destination=None, message_num=None, message_type=None, state=None, ascii_string=None):
        self.time = timestamp()
        self.source = None
        self.destination = None
        self.message_num = None
        self.message_type = None
        self.message_state = None
        self.checkpoint_count = None
        if ascii_string is not None:
            self.parse_data(ascii_string)
        elif (source is not None) and (destination is not None) and (message_num is not None) and (message_type is not None):
            self.source = source
            self.destination = destination
            self.message_num = message_num
            self.message_type = message_type
            self.message_state = state
            self.checkpoint_count = None
            if(message_type == "checkpoint"):
                self.message_state = state[0]
                self.checkpoint_count = state[1]

    def parse_data(self, data):
        data = data.split("\t")
        header = data[0].strip("<").strip(">")
        header_fields = header.split(", ")
        if len(header_fields) == 4:
            self.source = header_fields[0]
            self.destination = header_fields[1]
            self.message_num = header_fields[2]
            self.message_type = header_fields[3]
        self.message_state = None
        self.checkpoint_count = None
        if len(data) > 1:
            self.message_state = data[1].strip("<").strip(">")
            if self.message_type == "checkpoint" and len(data) > 2:
                self.checkpoint_count = data[2].strip("<").strip(">")
                

    def __repr__(self):
        string1 = f"<{self.source}, {self.destination}, {self.message_num}, {self.message_type}>"
        if self.message_state is None:
            return string1
        if self.message_type == "checkpoint":
            return string1 + f"\t<{self.message_state}>\t<{self.checkpoint_count}>"
        return string1 + f"\t<{self.message_state}>"

servers = {
    1: ServerEndpoint('', ServerPorts(10101, 10001)),
    2: ServerEndpoint('', ServerPorts(10102, 10002)),
    3: ServerEndpoint('', ServerPorts(10103, 10003)),
}

lfds = {
    1: ServerEndpoint('', 9901),
    2: ServerEndpoint('', 9902),
    3: ServerEndpoint('', 9903),
}

gfd = ServerEndpoint('', 10000)

rm = ServerEndpoint('', 10100)

client = MongoClient("mongodb://localhost:27017/")  # replace with your MongoDB URI
db = client["local"]  # replace with your database name

def check_and_update_collection_data(db_collection: Collection, component_id: int, data: list):
    """
    Checks if an entry with the specified serverId exists in the collection.
    If it doesn't exist, it creates a new entry with serverId and serverPerformance.
    If it does exist, it appends the performance_data to the serverPerformance array.
    """
    query = {"componentId": component_id}
    update = {
        "$push": data
    }
    upsert = True  # This will insert a new document if one doesn't exist

    db_collection.update_one(query, update, upsert=upsert)