use strict;
use warnings;
use inc::Module::Install;

name 'SeatingList';
version '0.1';
author 'Aki <aki@nekoruri.jp>';

license 'perl';
requires 'Mojolicious::Lite';
requires 'Net::Twitter::Lite';
requires 'Data::Dumper';
requires 'WebService::Simple';
requires 'Cache::File';
requires 'DBI';
test_requires 'Test::More';
test_requires 'DBD::SQLite';

WriteAll;
