from http.server import HTTPSServer, SimpleHTTPRequestHandler, test
import sys




class CORSRequestHandler (SimpleHTTPRequestHandler):
    def end_headers (self):
        self.send_header('Access-Control-Allow-Origin', '*')
        SimpleHTTPRequestHandler.end_headers(self)

if __name__ == '__main__':
    test(CORSRequestHandler, HTTPSServer, port=7788,tls_cert="cert.pem",tls_key="key.pem")
