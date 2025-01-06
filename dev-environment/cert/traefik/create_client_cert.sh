#!/bin/bash
openssl genrsa -out client.key 8192
openssl req -new -key client.key -out client.csr -utf8 -nameopt multiline,utf8 -subj "/C=DK/ST=Midtjylland/L=Århus/O=Magenta ApS/CN=Suila Dev Client" -addext "extendedKeyUsage = clientAuth"
openssl ca -config ca.conf -in client.csr -cert ca.cert -keyfile ca.key -out client.cert -batch -md sha512
