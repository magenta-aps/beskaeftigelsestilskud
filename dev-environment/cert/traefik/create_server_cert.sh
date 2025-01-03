#!/bin/bash
openssl genrsa -out server.key 1024
openssl req -new -key server.key -out server.csr
openssl ca -config ca.conf -in server.csr -cert ca.cert -keyfile ca.key -out server.crt
