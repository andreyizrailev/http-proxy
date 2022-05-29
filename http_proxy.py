import socket
import threading
import httptools
import select

HOST = 'localhost'
PORT = 4343

class HttpToolsProtocol:
    def __init__(self):
        self.message_complete = False

    def on_url(self, url):
        self.url = url

    def on_message_complete(self):
        self.message_complete = True

def handle_connection(client_socket):
    offset = -1
    first_transaction = b''
    proto = HttpToolsProtocol()
    parser = httptools.HttpRequestParser(proto)
    server_socket = None

    # Obtain the first HTTP(S) transaction
    while True:
        data = client_socket.recv(4096)
        if len(data) == 0:
            client_socket.close()
            if not proto.message_complete:
                print('HTTP(S) request too short')
            return
        first_transaction += data

        try:
            parser.feed_data(data)
        except httptools.HttpParserUpgrade as e:
            offset = e.args[0]
        except Exception as e:
            print('Unhandled exception: ', e)
            client_socket.close()
            return

        if proto.message_complete:
            try:
                if b'://' not in proto.url:
                    proto.url = b'https://' + proto.url
                url = httptools.parse_url(proto.url)
            except Exception as e:
                print('Failed to parse url:', e)
                client_socket.close()
                return

            dst_host = url.host
            dst_port = url.port
            if dst_port == None:
                dst_port = 80
            print('Connection to host = {}, port = {}'.format(dst_host, dst_port))

            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            except Exception as e:
                print('Failed to open a socket, unhandled exception:', e)
                client_socket.close()
                return

            try:
                server_socket.connect((dst_host, dst_port))
            except Exception as e:
                print('Failed to connect a socket, unhandled exception:', e)
                client_socket.close()
                server_socket.close()
                return

            if parser.get_method() == b'CONNECT':
                ok_response = b'HTTP/' + bytes(parser.get_http_version(), 'UTF-8') + b' 200 OK \r\n\n'
                try:
                    client_socket.sendall(ok_response)

                    if offset != -1 and len(data) > offset:
                        server_socket.sendall(data[offset:])
                except Exception as e:
                    print('Failed to send data, unhandled exception:', e)
                    client_socket.close()
                    server_socket.close()
                    return
            else:
                try:
                    server_socket.sendall(first_transaction)
                except Exception as e:
                    print('Failed to send data, unhandled exception:', e)
                    client_socket.close()
                    server_socket.close()
                    return

            break

    assert server_socket != None
    server_socket.setblocking(False);
    client_socket.setblocking(False);
    read_sockets = [server_socket, client_socket]

    while True:
        readable, _, _ = select.select(read_sockets, [], [])
        for src in readable:
            dst = server_socket
            if src == server_socket:
                dst = client_socket

            try:
                data = src.recv(4096)
                if len(data) != 0:
                   dst.sendall(data)
            except Exception as e:
                print('Unhandled exception:', e)
                client_socket.close()
                server_socket.close()
                return

def main():
    try:
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except Exception as e:
        print('Failed to open a listening socket, unhandled exception:', e)
        return
    try:
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_socket.bind((HOST, PORT))
        listen_socket.listen()
    except Exception as e:
        print('Unhandled exception:', e)
        listen_socket.close()
        return

    while True:
        try:
            client_socket, addr = listen_socket.accept()
        except Exception as e:
            print('Failed to accept a connection, unhandled exception:', e)
            return

        print('New connection from ' + str(addr))
        t = threading.Thread(target = handle_connection, args = (client_socket,), daemon = True)
        t.start()

if __name__ == "__main__":
    main()
