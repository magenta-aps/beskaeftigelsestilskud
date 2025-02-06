#!/bin/bash

hosts_file="/hosts"

add_hosts=""
for hostname in suila-web-public suila-web-private suila-idp suila-mailhog suila-traefik api.suila-traefik; do
  if ! grep $hostname $hosts_file; then
    add_hosts+=" $hostname"
  fi
done

if [ ! -z "$add_hosts" ]; then
    echo "127.0.0.1       $add_hosts    # Suila hosts" >> $hosts_file
fi
