#!/usr/bin/env perl
use strict;
use warnings;

use Data::Dumper;
use Test::More tests => 3;

use lib 'lib';
use SeatingList::Model::DB;

my $config = {
    db_dsn => 'dbi:SQLite:',
    db_username => '',
    db_password => '',
};

my $db = SeatingList::Model::DB->new;
$db->init($config);


# 初期データ投入
my $dbh = $db->dbh;
$dbh->do(<<'END_SQL');
CREATE TABLE events (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    URL TEXT,
    seats_X TINYINT UNSIGNED NOT NULL,
    seats_Y TINYINT UNSIGNED NOT NULL,
    atnd_event_id INTEGER UNSIGNED DEFAULT NULL
);
END_SQL

$dbh->do(<<'END_SQL');
CREATE TABLE seats (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_id INT UNSIGNED NOT NULL,
    seat_X TINYINT UNSIGNED NOT NULL,
    seat_Y TINYINT UNSIGNED NOT NULL,
    twitter_user_id INT UNSIGNED NOT NULL,
    registered_at DATETIME NOT NULL,
    unregistered_at DATETIME NULL,
    is_enabled TINYINT(1) NOT NULL DEFAULT 1,
    is_machismo TINYINT(1) NULL
);
END_SQL

$dbh->do(<<'END_SQL');
CREATE TABLE twitter_user_cache (
    user_id INT UNSIGNED PRIMARY KEY,
    screen_name VARCHAR(255) NOT NULL,
    profile_image_url TEXT
);
END_SQL

$dbh->do(q{INSERT INTO events ( id, title, description, URL, seats_X, seats_Y ) VALUES ( 1, 'テストイベント', 'Hello, world', 'http://example.jp', 3, 3 );});
$dbh->do(q{INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, registered_at ) VALUES ( 1, 0, 0, 9999, '2010-01-01 00:00:00' );});
$dbh->do(q{INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, registered_at, is_enabled ) VALUES ( 1, 1, 1, 0, '2010-01-02 00:00:00', 0 );});
$dbh->do(q{INSERT INTO twitter_user_cache ( user_id, screen_name, profile_image_url ) VALUES ( 9999, 'testuser', 'http://example.jp/profile_images/9999/profile.jpg' );});

# seatsに個別登録した座席のテスト
my $table = $db->generate_seats(1);
is $table->[0][0]{user_id}, 9999, '初期データに含まれる座席が登録されていること';
is $table->[1][1]{is_enabled}, 0, '初期データに含まれる無効席が正しく無効化されていること';

# 配列全体のテスト
my $expected_seats = [
    [ {
        'is_enabled' => 1,
        'profile_image_url' => 'http://example.jp/profile_images/9999/profile.jpg',
        'is_machismo' => undef,
        'user_id' => 9999,
        'screen_name' => 'testuser'
      }, undef, undef ],
    [ undef, { 'is_enabled' => 0 }, undef ],
    [ undef, undef, undef ]
];
is_deeply $table, $expected_seats, '初期データから生成した座席表が正しく出力されること';

