#!/usr/bin/env perl
use strict;
use warnings;

use Data::Dumper;
use Test::More tests => 11;

use lib 'lib';
BEGIN { use_ok('SeatingList::Model::DB') }

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


# イベント一覧
my $events = $db->search_all_events;
my $expected_events =  [ { 'title' => 'テストイベント', 'id' => 1 } ];
is_deeply $events, $expected_events, '初期データから生成したイベント一覧が正しく出力されること';

# [異常時] seatsに個別登録した座席のテスト
is $db->generate_seats(), undef, 'generage_seatsの引数を忘れたらundefを返すこと';

# seatsに個別登録した座席のテスト
my $table = $db->generate_seats(1);
is $table->[0][0]{user_id}, 9999, '初期データに含まれる座席が登録されていること';
is $table->[1][1]{is_enabled}, 0, '初期データに含まれる無効席が正しく無効化されていること';
is $table->[0][0]{is_machismo}, undef, '初期データに含まれる座席がマッチョ非登録であること';

# 配列全体のテスト
#     0 1 2
# 0 [ U X X ] U: User
# 1 [ X D X ] D: Disabled
# 2 [ X X X ]
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


# 座席の無効化、有効化
$db->disable_seat(1, 0, 1);
$table = $db->generate_seats(1);
is $table->[0][1]{is_enabled}, 0, '無効化した座席が無効になっていること';

$db->enable_seat(1, 0, 1);
$table = $db->generate_seats(1);
isnt $table->[0][1]{is_enabled}, 0, '有効化した座席が有効になっていること';

# マッチョ機能
$db->machismo_seat(1, 0, 0);
$table = $db->generate_seats(1);
is $table->[0][0]{is_machismo}, 1, '座席をマッチョにできること';

$db->nomachismo_seat(1, 0, 0);
$table = $db->generate_seats(1);
is $table->[0][0]{is_machismo}, 0, '座席をウィンプにできること';

# 既存ユーザーの移動
#     0 1 2
# 0 [ X U X ] U: User
# 1 [ X D X ] D: Disabled
# 2 [ X X X ]
my $user = {
    id => 9999,
    screen_name => 'testuser',
    profile_image_url => 'http://example.jp/profile_images/9999/profile.jpg',
};
$db->update_seat($user, 1, 0, 1);
$table = $db->generate_seats(1);
is $table->[0][1]{user_id}, 9999, '移動元の座席が登録解除されていること';
isnt $table->[0][0]{user_id}, 9999, '移動先の座席が登録されていること';

# 別ユーザーの追加
#     0 1 2
# 0 [ X U N ] U: User
# 1 [ X D X ] D: Disabled
# 2 [ X X X ]
my $newuser = {
    id => 99999,
    screen_name => 'newuser',
    profile_image_url => 'http://example.jp/profile_images/99999/profile.png',
};
$db->update_seat($newuser, 1, 0, 2);
$table = $db->generate_seats(1);
is $table->[0][2]{user_id}, 99999, '登録した座席が登録されていること';

# 座席の登録解除
$db->remove_seat(1, 0, 0);
$table = $db->generate_seats(1);
is $table->[0][0]{user_id}, undef, '登録削除した座席が空席になっていること';

