#!/bin/bash
openssl genrsa -out client.key 1024
openssl req -new -key client.key -out client.csr -utf8 -nameopt multiline,utf8 -subj "/C=DK/ST=Midtjylland/L=Århus/O=Magenta ApS/CN=Suila Dev Client"
openssl ca -config ca.conf -in client.csr -cert ca.cert -keyfile ca.key -out client.cert -batch
