#!/usr/bin/env perl

use utf8;
use Mojolicious::Lite;
use Net::Twitter::Lite;
use Data::Dumper;
use Config::Pit;
use WebService::Simple;
use Cache::File;

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
        # Sign in with Twitter
        my $callback_url = $self->url_for('authorized')->to_abs;
        if (my $event_id = $self->param('event_id')) {
            $callback_url .= "?event_id=$event_id";
        }
        start_authorization($self, $callback_url);
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
get '/:event_id' => [event_id => qr/\d+/] => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');

    my ( $event, $seats ) = $db->generate_seats($event_id);

    $self->stash(screen_name => '');
    my $user = verify_credentials($self);
    if ($user) {
        $self->stash(screen_name => $user->{screen_name});
    }

    my $atnd_event_id = $event->{atnd_event_id};
#warn( "atnd_event_id: $atnd_event_id" );
    if ( $atnd_event_id ) {
        my $atnd_api_url = 'http://api.atnd.org/events/';
        my $cache_root = app->home->rel_file('tmp/cache');
        if ( ! -d $cache_root ) {
            mkdir $cache_root;
        }
        my $cache   = Cache::File->new(
            cache_root      => $cache_root,
            default_expires => '30 min',
        );
        my $atnd = WebService::Simple->new(
            base_url => $atnd_api_url,
#            cache => $cache,
            param => {},
        );
        my $response = $atnd->get({ event_id => $atnd_event_id });
#warn Dumper($response);
        my $atnd_event = $response->parse_response->{events}{event};
        $self->stash(atnd_event => $atnd_event);
    } else {
        $self->stash(atnd_event => undef);
    }

    $self->stash(admin => 0);
    $self->stash(event => $event);
    $self->stash(seats => $seats);
    $self->stash(enquetes => $db->fetch_event_enquetes($event_id));
    $self->render('event');
} => 'event';

# イベント管理画面
get '/:event_id/admin' => [event_id => qr/\d+/] => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');

    my $user = verify_credentials($self);
    if (!$user) {
        # 認証が無効ならば、request_tokenをもらってauthorization開始
        my $callback_url = $self->url_for('index')->to_abs . "$event_id/admin/authorized";
        start_authorization($self, $callback_url);
        return;
    }
    my ( $event, $seats ) = $db->generate_seats($event_id);
    if ( $event->{owner_twitter_user_id} ne $user->{id_str} ) {
        # 管理者じゃなければイベント画面にリダイレクト
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
        return;
    }            

    $self->stash(screen_name => $user->{screen_name});
    $self->stash(atnd_event => undef);
    $self->stash(admin => 1);
    $self->stash(event => $event);
    $self->stash(seats => $seats);
    $self->stash(error => {});
    $self->stash(enquetes => $db->fetch_event_enquetes($event_id));
    $self->render('event_admin');
} => 'event_admin';

# イベント情報の更新
post '/:event_id' => [event_id => qr/\d+/] => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');

    my $user = verify_credentials($self);
    if (!$user) {
        # 認証が無効ならばイベント画面にリダイレクト
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
        return;
    }
    my ( $event, $seats ) = $db->generate_seats($event_id);
    if ( $event->{owner_twitter_user_id} ne $user->{id_str} ) {
        # 管理者じゃなければイベント画面にリダイレクト
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
        return;
    }            

    #$self->app->log->debug(Dumper($self->param));
    #$self->app->log->debug(Dumper($seats));
    #n Dumper($self->param);

    # disabled[x][y] で無効にする席が入ってくるので、
    # $seats と比較して座席の有効・無効を更新する。
    foreach my $x ( 0 ... $event->{seats_X}-1 ) {
        foreach my $y ( 0 ... $event->{seats_Y}-1 ) {
            my $enabled_prev = $seats->[$x][$y] ? $seats->[$x][$y]{is_enabled} : 1;
            my $enabled_next = $self->param("disabled[$x][$y]") ? 0 : 1;
            if ($enabled_prev == 0 && $enabled_next == 1) {
                $self->app->log->debug("$x:$y | $enabled_prev => $enabled_next");
                $db->enable_seat($event_id, $x, $y);
            } elsif ($enabled_prev == 1 && $enabled_next == 0) {
                $self->app->log->debug("$x:$y | $enabled_prev => $enabled_next");
                $db->disable_seat($event_id, $x, $y);
            }
        }
    }

    # テキストフィールドからイベント情報を更新
    my @cols = qw( title seats_X seats_Y atnd_event_id description URL );
    $self->app->log->debug(Dumper([ map {$self->param($_)} @cols ]));

    my $event_info = { map {$_, $self->param($_) || undef} @cols };

    # バリデーション
    my $error = $db->validate_event($event_info);
    if ($error) {
        $self->app->log->debug(Dumper($error));
        $self->stash(screen_name => $user->{screen_name});
        $self->stash(atnd_event => undef);
        $self->stash(admin => 1);
        $self->stash(event => $event);
        $self->stash(seats => $seats);
        $self->stash(enquetes => $db->fetch_event_enquetes($event_id));
        $self->stash(error => $error);
        $self->render('event_admin');
        return;
    }

    # DBに保存
    $db->update_event($event_id, $event_info);

    # 終わったら管理画面にリダイレクト
    $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
};

# 座席登録(Twitter認証からのコールバック先)
get '/:event_id/admin/authorized' => [event_id => qr/\d$/] => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');

    my $verifier = $self->param('oauth_verifier');
    if ($verifier) {
        request_access_token($self, $verifier);
        if ( my $user = $tw->verify_credentials ) {
            $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
        }
    }
    $self->flash(error_message => 'Twitter認証に失敗しました。');
    $self->redirect_to($self->url_for('event')->to_abs."$event_id");
};

# 座席表に席を登録
get '/:event_id/seat/:x/:y' => [event_id => qr/\d+/] => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    if ( my $user = verify_credentials($self) ) {
        # 認証されていれば座席を登録
        $db->update_seat($user, $event_id, $seat_X, $seat_Y);
        $self->redirect_to($self->url_for('event')->to_abs."$event_id");
        return;
    } else {
        # 認証が無効ならば、request_tokenをもらってauthorization開始
        my $callback_url = $self->url_for('index')->to_abs . "$event_id/seat/$seat_X/$seat_Y/authorized";
        start_authorization($self, $callback_url);
    }
};

# 座席情報の編集
post '/:event_id/seat/:x/:y' => [event_id => qr/\d+/] => sub {
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
get '/:event_id/seat/:x/:y/authorized' => [event_id => qr/\d+/] => sub {
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
get '/:event_id/seat/:x/:y/disable' => [event_id => qr/\d+/] => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    $db->disable_seat($event_id, $seat_X, $seat_Y);
    $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
};

# 座席を有効化
get '/:event_id/seat/:x/:y/enable' => [event_id => qr/\d+/] => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');
    my $seat_X = $self->param('x');
    my $seat_Y = $self->param('y');

    $db->enable_seat($event_id, $seat_X, $seat_Y);
    $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
};

# アンケートフォームを表示
get '/:event_id/enquete_form' => [event_id => qr/\d+/] => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');

    my $user = eval { verify_credentials($self) };
    if (!$user) { 
        $self->render('event_enquete_nologin');
        return;
    }

    $self->stash(enquetes => $db->fetch_event_enquetes($event_id));

    $self->render('event_enquete_form');
} => 'event_enquete_form';

# アンケートの回答
post '/:event_id/enquete' => [event_id => qr/\d+/] => sub {
    my $self = shift;
    my $event_id = $self->param('event_id');

    my $user = eval { verify_credentials($self) };
    if (!$user) { 
        $self->render('event_enquete_nologin');
        return;
    }

    my $enquetes = $db->fetch_event_enquetes($event_id);
    my @enquete_ids = map { $_->{id} } @$enquetes;

    my $result = {};
    foreach my $enquete_id ( @enquete_ids ) {
        my $opt = $self->param('enq'.$enquete_id);
        if ( defined $opt ) {
            $result->{$enquete_id} = $opt;
        }
    }

    $db->enquete_update($event_id, $user, $result);
    $self->render('event_enquete_done');
} => 'event_enquete';

post '/create' => sub {
    my $self = shift;

    $self->app->log->debug(1);
    my $user = verify_credentials($self);
    if (!$user) {
        $self->redirect_to($self->url_for('index')->to_abs);
        return;
    }

    # テキストフィールドからイベント情報を更新
    my @cols = qw( title seats_X seats_Y atnd_event_id description URL );

    my $event_info = { map {$_, $self->param($_) || undef} @cols };
    $event_info->{owner_twitter_user_id} = $user->{id};
    $self->app->log->debug(Dumper($event_info));
    my $error = $db->validate_event($event_info);
    if ($error) {
        $self->app->log->debug(Dumper($error));
        $self->stash(error => $error);
        $self->stash(user => $user);
        $self->render('create_form');
    } else {
        my $event_id = $db->insert_event($event_info);
        $self->redirect_to($self->url_for('event')->to_abs."$event_id/admin");
    }
    
} => 'create_exec';

get '/create' => sub {
    my $self = shift;

    my $verifier = $self->param('oauth_verifier');
    if ($verifier) {
        request_access_token($self, $verifier);
        $self->redirect_to($self->url_for('create_form')->to_abs);
        return;
    }

    my $user = verify_credentials($self);
    if (!$user) {
        # Sign in with Twitter
        my $callback_url = $self->url_for('create_form')->to_abs;
        start_authorization($self, $callback_url);
        return;
    }

    $self->stash(error => {});
    $self->stash(user => $user);
    
} => 'create_form';


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

sub start_authorization
{
    my $self = shift;
    my $callback_url = shift;

    my $auth_url = $tw->get_authentication_url(callback => $callback_url);

    $self->session('tw_access_token' => '');
    $self->session('tw_access_token_secret' => '');
    $self->session('tw_request_token' => $tw->request_token);
    $self->session('tw_request_token_secret' => $tw->request_token_secret);

    $self->redirect_to($auth_url);
}

