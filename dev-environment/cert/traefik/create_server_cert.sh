#!/bin/bash
openssl genrsa -out server.key 1024
openssl req -new -key server.key -out server.csr -utf8 -nameopt multiline,utf8 -subj "/C=DK/ST=Midtjylland/L=Århus/O=Magenta ApS/CN=Suila Dev Server"
openssl ca -config ca.conf -in server.csr -cert ca.cert -keyfile ca.key -out server.cert -batch
