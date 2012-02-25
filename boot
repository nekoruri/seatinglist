#!/bin/sh
#perl seats.cgi daemon --reload --clients 100
starman seats.cgi --daemonize --access-log access.log --error-log error.log --port 3000
