#!/usr/bin/env perl

use utf8;
use Mojolicious::Lite;
use Net::Twitter::Lite;
use Data::Dumper;
use Config::Pit;
use WebService::Simple;

use lib app->home->rel_file('lib');
use SeatingList::Model::DB;

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

my $db = SeatingList::Model::DB->new;
$db->init($config);

# イベント一覧を表示(ID順)
get '/' => sub {
    my $self = shift;
    $self->render(events => $db->search_all_events());
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

    my ( $event, $seats ) = $db->generate_seats($event_id);

    $self->stash(screen_name => '');
    my $user = verify_credentials($self);
    if ($user) {
        $self->stash(screen_name => $user->{screen_name});
    }

    my $atnd_event_id = $event->{atnd_event_id};
warn( "atnd_event_id: $atnd_event_id" );
    if ( $atnd_event_id ) {
        my $atnd_api_url = 'http://api.atnd.org/events/';
        my $atnd = WebService::Simple->new(
            base_url => $atnd_api_url,
            param => {},
        );
        my $atnd_event = $atnd->get({ event_id => $atnd_event_id })->parse_response->{events}{event};
        $self->stash(atnd_event => $atnd_event);
    } else {
        $self->stash(atnd_event => undef);
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

    my ( $event, $seats ) = $db->generate_seats($event_id);

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

        if ( my $user = $tw->verify_credentials ) {
            $db->update_seat($user, $event_id, $seat_X, $seat_Y);
        }
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

# 座席情報の編集
post '/:event_id/seat/:x/:y' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    if ($self->param('remove')) {
        $db->remove_seat($event_id, $seat_X, $seat_Y);
    } elsif ($self->param('machismo')) {
        $db->machismo_seat($event_id, $seat_X, $seat_Y);
    } elsif ($self->param('nomachismo')) {
        $db->nomachismo_seat($event_id, $seat_X, $seat_Y);
    }
    $self->redirect_to($self->url_for('event')->to_abs."$event_id");
};

# 座席登録(Twitter認証からのコールバック先)
get '/:event_id/seat/:x/:y/authorized' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    my $verifier = $self->param('oauth_verifier');
    if ($verifier) {
        request_access_token($self, $verifier);
        if ( my $user = $tw->verify_credentials ) {
            $db->update_seat($user, $event_id, $seat_X, $seat_Y);
        }
    }
    $self->redirect_to($self->url_for('event')->to_abs."$event_id");
};

# 座席を無効化
get '/:event_id/seat/:x/:y/disable' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    $db->disable_seat($event_id, $seat_X, $seat_Y);
    $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
};

# 座席を有効化
get '/:event_id/seat/:x/:y/enable' => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    $db->enable_seat($event_id, $seat_X, $seat_Y);
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


