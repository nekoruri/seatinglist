#!/usr/bin/env perl

use utf8;
use Mojolicious::Lite;
use Net::Twitter::Lite;
use DBI;
use Data::Dumper;
use Config::Pit;

my $config = pit_get("seatinglist" , require => {
    consumer_key => 'Twitter consumer_key',
    consumer_secret => 'Twitter consumer_secret',
    db_dsn => 'Database data source name',
    db_username => 'Database username',
    db_password => 'Database password',
});

my $tw = Net::Twitter::Lite->new(
    consumer_key => $config->{consumer_key},
    consumer_secret => $config->{consumer_secret},
);

my $dbh = DBI->connect(
    $config->{db_dsn},
    $config->{db_username},
    $config->{db_password},
    { mysql_enable_utf8 => 1 }
);

# イベント一覧を表示(ID順)
get '/' => sub {
    my $self = shift;
    $self->render(events => search_all_events());
} => 'index';

get '/login' => sub {
    my $self = shift;

    my $user = verify_credentials($self);
    if ($user) {
        # 既にログインしていれば何もせず戻る。
        if ( my $event_id = $self->param('event_id') ) {
            $self->redirect_to($self->url_for('event')->to_abs."$event_id");
        } else {
            $self->redirect_to($self->url_for('index')->to_abs);
        }
    } else {
        # ひとまず今のアクセストークン対を忘れる。
        $self->session('tw_access_token' => '');
        $self->session('tw_access_token_secret' => '');

        # Sign in with Twitter
        my $callback_url = $self->url_for('authorized')->to_abs;
        if (my $event_id = $self->param('event_id')) {
            $callback_url .= "?event_id=$event_id";
        }
        my $auth_url = $tw->get_authentication_url(callback => $callback_url);
        $self->session('tw_request_token' => $tw->request_token);
        $self->session('tw_request_token_secret' => $tw->request_token_secret);

        $self->redirect_to($auth_url);
    }
} => 'login';

get '/authorized' => sub {
    my $self = shift;

    my $verifier = $self->param('oauth_verifier');
    if ($verifier) {
        request_access_token($self, $verifier);
    }
    if ( my $event_id = $self->param('event_id') ) {
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
    } else {
        $self->redirect_to($self->url_for('index')->to_abs);
    }
} => 'authorized';

get '/logout' => sub {
    my $self = shift;
    $self->session(expires => 1);
    if ( my $event_id = $self->param('event_id') ) {
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
    } else {
        $self->redirect_to($self->url_for('index')->to_abs);
    }
} => 'logout';

# イベントの座席表を表示
get '/:event_id' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');

    my ( $event, $seats ) = generate_seats($event_id);

    $self->stash(screen_name => '');
    my $user = verify_credentials($self);
    if ($user) {
        $self->stash(screen_name => $user->{screen_name});
    }

    $self->stash(admin => 0);
    $self->stash(event => $event);
    $self->stash(seats => $seats);
    $self->render('event');
} => 'event';

# イベントの座席表を表示
get '/:event_id/admin' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
#    $self->render(text => "event_id: $event_id\n");

    my ( $event, $seats ) = generate_seats($event_id);

    $self->stash(screen_name => '');
    eval {
        # Twitterの認証が有効かを確認
        my $tw_access_token = $self->session('tw_access_token');
        my $tw_access_token_secret = $self->session('tw_access_token_secret');
        if ( $tw_access_token && $tw_access_token_secret ) {
            $tw->access_token($tw_access_token);
            $tw->access_token_secret($tw_access_token_secret);
            if ( my $user = $tw->verify_credentials ) {
                $self->stash(screen_name => $user->{screen_name});
            }
        }
    };

    $self->stash(admin => 1);
    $self->stash(event => $event);
    $self->stash(seats => $seats);
    $self->render('event');
} => 'event_admin';

# 座席表に席を登録
get '/:event_id/seat/:x/:y' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    # Twitterの認証が有効かを確認
    my $tw_access_token = $self->session('tw_access_token');
    my $tw_access_token_secret = $self->session('tw_access_token_secret');

    if ( $tw_access_token && $tw_access_token_secret ) {
        $tw->access_token($tw_access_token);
        $tw->access_token_secret($tw_access_token_secret);

        update_seat($event_id, $seat_X, $seat_Y);
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
        return;
    }

    # 無効ならば、request_tokenをもらってauthorization開始
    my $callback_url = $self->url_for('index')->to_abs . "$event_id/seat/$seat_X/$seat_Y/authorized";
    my $auth_url = $tw->get_authentication_url(callback => $callback_url);

    $self->session('tw_request_token' => $tw->request_token);
    $self->session('tw_request_token_secret' => $tw->request_token_secret);

    $self->redirect_to($auth_url);
};

post '/:event_id/seat/:x/:y' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    if ($self->param('remove')) {
        remove_seat($event_id, $seat_X, $seat_Y);
    } elsif ($self->param('machismo')) {
        machismo_seat($event_id, $seat_X, $seat_Y);
    } elsif ($self->param('nomachismo')) {
        nomachismo_seat($event_id, $seat_X, $seat_Y);
    }
    $self->redirect_to($self->url_for('event')->to_abs."$event_id");
};

get '/:event_id/seat/:x/:y/authorized' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    my $verifier = $self->param('oauth_verifier');
    if ($verifier) {
        request_access_token($self, $verifier);
        update_seat($event_id, $seat_X, $seat_Y);
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
    }
#    $self->redirect_to('event');
};


get '/:event_id/seat/:x/:y/disable' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    disable_seat($event_id, $seat_X, $seat_Y);
    $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
};

get '/:event_id/seat/:x/:y/enable' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    enable_seat($event_id, $seat_X, $seat_Y);
    $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
};

app->types->type(html => 'text/html; charset=utf-8');
app->start;

# Twitterのアクセストークンを取得してセッションに保存
sub request_access_token
{
    my ( $self, $verifier ) = @_;
    $tw->request_token( $self->session('tw_request_token') );
    $tw->request_token_secret( $self->session('tw_request_token_secret' ) );

    eval { 
        my ($access_token, $access_token_secret, $user_id, $screen_name) = $tw->request_access_token(verifier => $verifier);

        $self->session(tw_access_token => $access_token);
        $self->session(tw_access_token_secret => $access_token_secret);
    }; if ($@) {
        warn Dumper($@);
    }
}

# 自分のユーザ情報を取得
sub verify_credentials
{
    my $self = shift;
    eval {
        # Twitterの認証が有効かを確認
        my $tw_access_token = $self->session('tw_access_token');
        my $tw_access_token_secret = $self->session('tw_access_token_secret');
        if ( $tw_access_token && $tw_access_token_secret ) {
            $tw->access_token($tw_access_token);
            $tw->access_token_secret($tw_access_token_secret);
            if ( my $user = $tw->verify_credentials ) {
                return $user;
            }
        }
    };
}

sub generate_seats
{
    my ( $event_id ) = @_;

    my $sql = 'SELECT title, seats_X, seats_Y FROM events WHERE id = ?';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id);

    my $event = $sth->fetchrow_hashref;
    my $seats_X = $event->{seats_X};
    my $seats_Y = $event->{seats_Y};

    # 座席表初期化
    # $seats->[seat_X][seat_Y] = { user_id => $user_id, ... }
    my $seats = [];
    foreach my $i ( 0 ... $seats_X-1 ) {
        $seats->[$i][$seats_Y-1] = undef;
    }

    $sql = 'SELECT seat_X, seat_Y, user_id, screen_name, profile_image_url, is_enabled, is_machismo FROM seats LEFT JOIN twitter_user_cache ON seats.twitter_user_id = twitter_user_cache.user_id WHERE event_id = ? AND unregistered_at IS NULL ORDER BY registered_at';
    $sth = $dbh->prepare($sql);
    $sth->execute($event_id);

    $event->{machismo} = 0;
    $event->{nomachismo} = 0;
    while (my @row = $sth->fetchrow_array) {
        # X,Yが同じものは新しい値で上書き
        if ( $row[5] ) {
            # 座席情報
            $seats->[$row[0]][$row[1]] = { user_id => $row[2], screen_name => $row[3], profile_image_url => $row[4], is_enabled => 1, is_machismo => $row[6] };
            if ( defined($row[6]) ) {
                if ( $row[6] == 1 ) {
                    $event->{machismo}++;
                } else {
                    $event->{nomachismo}++;
                }
            }
        } else { 
            # 予約席
            $seats->[$row[0]][$row[1]] = { is_enabled => 0 };
        }
    }
#warn Dumper($seats);
    return ($event, $seats);
}

sub update_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    if ( my $user = $tw->verify_credentials ) {
        # 有効ならば、そのまま席を登録
        my $user_id = $user->{id};
        my $screen_name = $user->{screen_name};
        my $profile_image_url = $user->{profile_image_url};

        # 以前座っていた席を無効化
        my $sql = 'UPDATE seats SET unregistered_at = NOW() WHERE event_id = ? AND twitter_user_id = ?';
        my $sth = $dbh->prepare($sql);
        $sth->execute($event_id, $user_id);

        # 座席情報を追加 (置き換えはしない)
        $sql = 'INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, registered_at ) VALUE ( ?, ?, ?, ?, NOW() )';
        $sth = $dbh->prepare($sql);
        $sth->execute($event_id, $seat_X, $seat_Y, $user_id);

        # Twitterユーザ情報キャッシュを更新
        # user_idがプライマリキーなので既存レコードがあれば更新
        $sql = 'REPLACE INTO twitter_user_cache ( user_id, screen_name, profile_image_url ) VALUE ( ?, ?, ? )';
        $sth = $dbh->prepare($sql);
        $sth->execute($user_id, $screen_name, $profile_image_url);

        return;
    }

}

sub disable_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'INSERT INTO seats ( event_id, seat_X, seat_Y, twitter_user_id, registered_at, is_enabled ) VALUE ( ?, ?, ?, 0, NOW(), 0 )';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub enable_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET unregistered_at = NOW() WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 0 AND unregistered_at IS NULL';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub remove_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET unregistered_at = NOW() WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub machismo_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET is_machismo = 1 WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

sub nomachismo_seat
{
    my ( $event_id, $seat_X, $seat_Y ) = @_;

    my $sql = 'UPDATE seats SET is_machismo = 0 WHERE event_id = ? AND seat_X = ? AND seat_Y = ? AND is_enabled = 1 AND unregistered_at IS NULL';
    my $sth = $dbh->prepare($sql);
    $sth->execute($event_id, $seat_X, $seat_Y);
}

# DB系ファサード

# 全てのイベントをID順に表示
sub search_all_events
{
    my $sql = 'SELECT id, title FROM events ORDER BY id';
    my $sth = $dbh->prepare($sql);
    $sth->execute();
    my $events = [];
    while (my @row = $sth->fetchrow_array) {
        my $event = {
            id => $row[0],
            title => $row[1],
        };
        push @$events, $event;
    }
    return $events;
}

