#!/bin/bash
openssl genrsa -out server.key 8192
openssl req -sha512 -new -key server.key -out server.csr -utf8 -nameopt multiline,utf8 -subj "/C=DK/ST=Midtjylland/L=Århus/O=Magenta ApS/CN=api.bf-traefik"
openssl ca -config ca.conf -in server.csr -cert ca.cert -keyfile ca.key -out server.cert -batch -md sha512
