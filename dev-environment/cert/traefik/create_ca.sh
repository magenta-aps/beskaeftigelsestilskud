#!/bin/bash
openssl genrsa -out ca.key 8192
openssl req -new -key ca.key -out ca.csr -sha512 -utf8 -nameopt multiline,utf8 -subj "/C=DK/ST=Midtjylland/L=Århus/O=Magenta ApS/CN=Suila Dev CA"
openssl x509 -req -days 10000 -sha512 -in ca.csr -out ca.cert -signkey ca.key
