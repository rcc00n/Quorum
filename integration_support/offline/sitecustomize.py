"""Opt-in test subprocess guard. Never installed into a production environment."""
import socket

def blocked(*args, **kwargs):
    raise OSError('OFFLINE TEST: network connection blocked')

socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
