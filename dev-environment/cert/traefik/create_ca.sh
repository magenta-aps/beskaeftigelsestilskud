 openssl genrsa -out ca.key 1024
 openssl req -new -key ca.key -out ca.csr
openssl x509 -req -days 10000 -in ca.csr -out ca.cert -signkey ca.key
