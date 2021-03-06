from base.database import get_obj
from base.properties import pretty_names
from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    url_for
)
from flask_login import login_required
from .forms import (
    AddUser,
    CreateAccountForm,
    LoginForm,
    SyslogServerForm,
    TacacsServerForm,
)
from .models import SyslogServer
from passlib.hash import cisco_type7
from .properties import user_properties, user_search_properties
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from tacacs_plus.client import TACACSClient
from tacacs_plus.flags import TAC_PLUS_AUTHEN_TYPE_ASCII
import flask_login

login_manager = flask_login.LoginManager()

blueprint = Blueprint(
    'admin_blueprint',
    __name__,
    url_prefix='/admin',
    template_folder='templates',
    static_folder='static'
)

from base.database import db
from .models import User, user_factory, TacacsServer

## Template rendering


@blueprint.route('/user_management')
@login_required
def users():
    form = AddUser(request.form)
    return render_template(
        'users_overview.html',
        fields=user_search_properties,
        names=pretty_names,
        users=User.query.all(),
        form=form
    )


@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = str(request.form['name'])
        password = str(request.form['password'])
        user = db.session.query(User).filter_by(name=name).first()
        if user and cisco_type7.verify(password, user.password):
            flask_login.login_user(user)
            return redirect(url_for('base_blueprint.dashboard'))
        else:
            try:
                # tacacs_plus does not support py2 unicode, hence the
                # conversion to string.
                # TACACSClient cannot be saved directly to session
                # as it is not serializable: this temporary fixes will create
                # a new instance of TACACSClient at each TACACS connection
                # attemp: clearly suboptimal, to be improved later.
                encrypted_password = cisco_type7.hash(password)
                tacacs_server = db.session.query(TacacsServer).one()
                tacacs_client = TACACSClient(
                    str(tacacs_server.ip_address),
                    int(tacacs_server.port),
                    str(cisco_type7.decode(str(tacacs_server.password)))
                )
                if tacacs_client.authenticate(
                    name,
                    password,
                    TAC_PLUS_AUTHEN_TYPE_ASCII
                ).valid:
                    user = User(name=name, password=encrypted_password)
                    db.session.add(user)
                    db.session.commit()
                    flask_login.login_user(user)
                    return redirect(url_for('base_blueprint.dashboard'))
            except NoResultFound:
                pass
        return render_template('errors/page_403.html')
    if not flask_login.current_user.is_authenticated:
        return render_template(
            'login.html',
            login_form=LoginForm(request.form),
            create_account_form=CreateAccountForm(request.form)
        )
    return redirect(url_for('base_blueprint.dashboard'))


@blueprint.route('/logout')
@login_required
def logout():
    flask_login.logout_user()
    return redirect(url_for('admin_blueprint.login'))


@blueprint.route('/administration')
@login_required
def admninistration():
    try:
        tacacs_server = db.session.query(TacacsServer).one()
    except NoResultFound:
        tacacs_server = None
    try:
        syslog_server = db.session.query(SyslogServer).one()
    except NoResultFound:
        syslog_server = None
    return render_template(
        'administration.html',
        tacacs_form=TacacsServerForm(request.form),
        syslog_form=SyslogServerForm(request.form),
        tacacs_server=tacacs_server,
        syslog_server=syslog_server
    )


## AJAX calls


@blueprint.route('/process_user', methods=['POST'])
def process_user():
    try:
        user_factory(**request.form.to_dict())
        return jsonify('success')
    except IntegrityError:
        return jsonify('duplicate')


@blueprint.route('/get_<name>', methods=['POST'])
@login_required
def get_user(name):
    user = get_obj(User, name=name)
    properties = {
        property: str(getattr(user, property))
        for property in user_properties if property != 'password'
    }
    return jsonify(properties)


@blueprint.route('/delete_<name>', methods=['POST'])
@login_required
def delete_user(name):
    user = get_obj(User, name=name)
    db.session.delete(user)
    db.session.commit()
    return jsonify({})


@blueprint.route('/save_tacacs_server', methods=['POST'])
@login_required
def save_tacacs_server():
    TacacsServer.query.delete()
    tacacs_server = TacacsServer(**request.form.to_dict())
    db.session.add(tacacs_server)
    db.session.commit()
    return jsonify({})


@blueprint.route('/save_syslog_server', methods=['POST'])
@login_required
def save_syslog_server():
    SyslogServer.query.delete()
    syslog_server = SyslogServer(**request.form.to_dict())
    db.session.add(syslog_server)
    db.session.commit()
    return jsonify({})
