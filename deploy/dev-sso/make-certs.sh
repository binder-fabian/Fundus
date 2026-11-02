#!/bin/sh
# Erzeugt eine Test-CA und ein Zertifikat für localhost (nur Entwicklung).
set -e
cd "$(dirname "$0")"
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=Fundus Test-CA" \
  -keyout certs/ca.key -out certs/ca.crt
openssl req -newkey rsa:2048 -nodes -subj "/CN=localhost" \
  -keyout certs/ldap.key -out certs/ldap.csr
printf "subjectAltName=DNS:localhost\n" > certs/san.ext
openssl x509 -req -in certs/ldap.csr -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
  -days 3650 -extfile certs/san.ext -out certs/ldap.crt
openssl dhparam -out certs/dhparam.pem 2048 2>/dev/null
chmod 644 certs/*
