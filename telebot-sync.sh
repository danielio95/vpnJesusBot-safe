#!/bin/bash
# Move to the directory
cd /usr/local/telebot

# Get today's date
DATE=$(date +'%Y-%m-%d')

# Execute git commands
git commit -am "update users.json $DATE"
git push
