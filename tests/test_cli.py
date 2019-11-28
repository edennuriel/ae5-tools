import pytest

import tempfile
import time
import os
import pytest
import pprint
import requests
import tarfile
import glob
import uuid

from datetime import datetime
from collections import namedtuple
from ae5_tools.api import AEUnexpectedResponseError

from .utils import _cmd, CMDException


Session = namedtuple('Session', 'hostname username')


@pytest.fixture
def project_list_cli(user_session):
    return _cmd('project list --collaborators')


def test_project_info(project_list_cli):
    for rec0 in project_list_cli:
        id = rec0['id']
        pair = '{}/{}'.format(rec0['owner'], rec0['name'])
        rec1 = _cmd(f'project info {id}')
        rec2 = _cmd(f'project info {pair}')
        rec3 = _cmd(f'project info {pair}/{id}')
        assert all(rec0[k] == v for k, v in rec2.items()), pprint.pformat((rec0, rec2))
        assert all(rec1[k] == v for k, v in rec2.items()), pprint.pformat((rec1, rec2))
        assert rec2 == rec3


def test_project_info_errors(user_session):
    with pytest.raises(CMDException) as excinfo:
        _cmd('project info testproj1')
    assert 'Multiple projects' in str(excinfo.value)
    with pytest.raises(CMDException) as excinfo:
        _cmd('project info testproj4')
    assert 'No projects' in str(excinfo.value)


def test_project_collaborators(user_session, project_list):
    uname = 'tooltest2'
    rec = next(rec for rec in project_list if not rec['collaborators'])
    id = rec['id']
    with pytest.raises(CMDException) as excinfo:
        _cmd(f'project collaborator info {id} {uname}')
    assert f'Collaborator not found: {uname}' in str(excinfo.value)
    clist = _cmd(f'project collaborator add {id} {uname}')
    assert len(clist) == 1
    clist = _cmd(f'project collaborator add {id} everyone --group --read-only')
    assert len(clist) == 2
    assert all(c['id'] == uname and c['permission'] == 'rw' and c['type'] == 'user' or
               c['id'] == 'everyone' and c['permission'] == 'r' and c['type'] == 'group'
               for c in clist)
    clist = _cmd(f'project collaborator add {id} {uname} --read-only')
    assert len(clist) == 2
    assert all(c['id'] == uname and c['permission'] == 'r' and c['type'] == 'user' or
               c['id'] == 'everyone' and c['permission'] == 'r' and c['type'] == 'group'
               for c in clist)
    for crec in clist:
        crec2 = _cmd(f'project collaborator info {id} {crec["id"]}')
        assert all(crec.get(k, '') == crec2.get(k, '') for k in set(crec) | set(crec2))
    clist = _cmd(f'project collaborator remove {id} {uname} everyone')
    assert len(clist) == 0
    with pytest.raises(CMDException) as excinfo:
        clist = _cmd(f'project collaborator remove {id} {uname}')
    assert f'Collaborator(s) not found: {uname}' in str(excinfo.value)


def test_resource_profiles(user_session):
    rlist = _cmd(f'resource-profile list')
    for rec in rlist:
        rec2 = _cmd(f'resource-profile info {rec["name"]}')
        assert rec == rec2


def test_editors(user_session):
    elist = _cmd(f'editor list')
    editors = set(rec['id'] for rec in elist)
    assert sum(rec['is_default'].lower() == 'true' for rec in elist) == 1
    assert editors.issuperset({'zeppelin', 'jupyterlab', 'notebook'})
    for rec in elist:
        rec2 = _cmd(f'editor info {rec["id"]}')
        assert rec == rec2


def test_samples(user_session):
    slist = _cmd(f'sample list')
    assert sum(rec['is_default'].lower() == 'true' for rec in slist) == 1
    assert sum(rec['is_template'].lower() == 'true' for rec in slist) > 1
    for rec in slist:
        rec2 = _cmd(f'sample info "{rec["id"]}"')
        rec3 = _cmd(f'sample info "{rec["name"]}"')
        assert rec == rec2 and rec == rec3


def test_sample_clone(user_session):
    uname = user_session.username
    cname = 'nlp_api'
    pname = 'testclone'
    rrec = _cmd(f'sample clone {cname} --name {pname}')
    _cmd(f'project delete {rrec["id"]} --yes', table=False)


@pytest.fixture(scope='module')
def downloaded_project(user_session):
    uname = user_session.username
    with tempfile.TemporaryDirectory() as tempd:
        fname = os.path.join(tempd, 'blob.tar.gz')
        fname2 = os.path.join(tempd, 'blob2.tar.gz')
        _cmd(f'project download {uname}/testproj1 --filename {fname}', table=False)
        with tarfile.open(fname, 'r') as tf:
            tf.extractall(path=tempd)
        dnames = glob.glob(os.path.join(tempd, '*', 'anaconda-project.yml'))
        assert len(dnames) == 1
        dname = os.path.dirname(dnames[0])
        yield fname, fname2, dname
    for r in user_session.project_list():
        if r['owner'] == uname and r['name'].startswith('test_upload'):
            _cmd(f'project delete {r["id"]} --yes', table=False)
    assert not any(r['owner'] == uname and r['name'].startswith('test_upload')
                   for r in _cmd('project list'))


def test_project_download(downloaded_project):
    pass


def test_project_upload(user_session, downloaded_project):
    fname, fname2, dname = downloaded_project
    _cmd(f'project upload {fname} --name test_upload1 --tag 1.2.3')
    rrec = _cmd(f'project revision list test_upload1')
    assert len(rrec) == 1
    assert rrec[0]['name'] == '1.2.3'
    _cmd(f'project download test_upload1 --filename {fname2}', table=False)


def test_project_upload_as_directory(user_session, downloaded_project):
    fname, fname2, dname = downloaded_project
    _cmd(f'project upload {dname} --name test_upload2 --tag 1.2.3')
    rrec = _cmd(f'project revision list test_upload2')
    assert len(rrec) == 1
    assert rrec[0]['name'] == '1.2.3'
    _cmd(f'project download test_upload2 --filename {fname2}', table=False)


@pytest.fixture(scope='module')
def cli_project(user_session):
    uname = user_session.username
    pname = 'testproj3'
    prec = _cmd(f'project info {uname}/{pname}')
    yield prec


def test_project_activity(cli_project):
    prec = cli_project
    activity = _cmd(f'project activity --limit -1 {prec["id"]}')
    assert activity[-1]['status'] == 'created'
    assert activity[-1]['done']
    assert activity[-1]['owner'] == prec['owner']
    activity2 = _cmd(f'project activity --latest {prec["id"]}')
    assert activity[0] == activity2


def test_project_revisions(cli_project):
    prec = cli_project
    revs = _cmd(f'project revision list {prec["id"]}')
    rev0 = _cmd(f'project revision info {prec["id"]}')
    assert revs[0] == rev0
    rev0 = _cmd(f'project revision info {prec["id"]}:latest')
    assert revs[0] == rev0
    for rev in revs:
        revN = _cmd(f'project revision info {prec["id"]}:{rev["id"]}')
        assert rev == revN


@pytest.fixture(scope='module')
def cli_session(user_session, cli_project):
    prec = cli_project
    srec = _cmd(f'session start {prec["owner"]}/{prec["name"]}')
    srec2 = _cmd(f'session restart {srec["id"]} --wait')
    assert not any(r['id'] == srec['id'] for r in _cmd('session list'))
    yield prec, srec2
    _cmd(f'session stop {srec2["id"]} --yes', table=False)
    assert not any(r['id'] == srec2['id'] for r in _cmd('session list'))


def test_session(user_session, cli_session):
    prec, srec = cli_session
    assert srec['owner'] == prec['owner'], srec
    assert srec['name'] == prec['name'], srec
    # Ensure that the session can be retrieved by its project ID as well
    srec2 = _cmd(f'session info {srec["owner"]}/*/{prec["id"]}')
    assert srec2['id'] == srec['id']
    endpoint = srec['id'].rsplit("-", 1)[-1]
    sdata = _cmd(f'call / --endpoint={endpoint}', table=False)
    assert 'Jupyter Notebook requires JavaScript.' in sdata, sdata


def test_project_sessions(user_session, cli_session):
    prec, srec = cli_session
    slist = _cmd(f'project sessions {prec["id"]}')
    assert len(slist) == 1 and slist[0]['id'] == srec['id']


def test_session_branches(user_session, cli_session):
    prec, srec = cli_session
    branches = _cmd(f'session branches {prec["id"]}')
    bdict = {r['branch']: r['sha1'] for r in branches}
    assert set(bdict) == {'local', 'origin/local', 'master'}, branches
    assert bdict['local'] == bdict['master'], branches


def test_session_before_changes(user_session, cli_session):
    prec, srec = cli_session
    changes1 = _cmd(f'session changes {prec["id"]}')
    assert changes1 == [], changes1
    changes2 = _cmd(f'session changes --master {prec["id"]}')
    assert changes2 == [], changes2


@pytest.fixture(scope='module')
def cli_deployment(user_session, cli_project):
    prec = cli_project
    dname = 'testdeploy'
    ename = 'testendpoint'
    drec = _cmd(f'project deploy {prec["owner"]}/{prec["name"]} --name {dname} --endpoint {ename} --command default --private')
    drec2 = _cmd(f'deployment restart {drec["id"]} --wait')
    assert not any(r['id'] == drec['id'] for r in _cmd('deployment list'))
    yield prec, drec2
    _cmd(f'deployment stop {drec2["id"]} --yes', table=False)
    assert not any(r['id'] == drec2['id'] for r in _cmd('deployment list'))


def test_deploy(user_session, cli_deployment):
    prec, drec = cli_deployment
    assert drec['owner'] == prec['owner'], drec
    assert drec['project_name'] == prec['name'], drec
    for attempt in range(3):
        try:
            ldata = _cmd(f'call / --endpoint {drec["endpoint"]}', table=False)
            break
        except AEUnexpectedResponseError:
            time.sleep(attempt * 5)
            pass
    else:
        raise RuntimeError("Could not get the endpoint to respond")
    assert ldata.strip() == 'Hello Anaconda Enterprise!', ldata


def test_project_deployments(user_session, cli_deployment):
    prec, drec = cli_deployment
    dlist = _cmd(f'project deployments {prec["id"]}')
    assert len(dlist) == 1 and dlist[0]['id'] == drec['id']


def test_deploy_patch(user_session, cli_deployment):
    prec, drec = cli_deployment
    flag = '--private' if drec['public'].lower() == 'true' else '--public'
    drec2 = _cmd(f'deployment patch {flag} {drec["id"]}')
    assert drec2['public'] != drec['public']
    flag = '--private' if drec2['public'].lower() == 'true' else '--public'
    drec3 = _cmd(f'deployment patch {flag} {drec["id"]}')
    assert drec3['public'] == drec['public']


def test_deploy_token(user_session, cli_deployment):
    prec, drec = cli_deployment
    token = _cmd(f'deployment token {drec["id"]}', table=False).strip()
    resp = requests.get(f'https://{drec["endpoint"]}.' + user_session.hostname,
                        headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.text.strip() == 'Hello Anaconda Enterprise!', resp.text


def test_deploy_logs(user_session, cli_deployment):
    prec, drec = cli_deployment
    id = drec['id']
    app_prefix = 'anaconda-app-' + id.rsplit("-", 1)[-1] + '-'
    app_logs = _cmd(f'deployment logs {id}', table=False)
    event_logs = _cmd(f'deployment logs {id} --events', table=False)
    proxy_logs = _cmd(f'deployment logs {id} --proxy', table=False)
    assert 'The project is ready to run commands.' in app_logs
    assert app_prefix in event_logs, event_logs
    assert 'App Proxy is fully operational!' in proxy_logs, proxy_logs


def test_deploy_duplicate(user_session, cli_deployment):
    prec, drec = cli_deployment
    dname = drec['name'] + '-dup'
    with pytest.raises(CMDException) as excinfo:
        _cmd(f'project deploy {prec["id"]} --name {dname} --endpoint {drec["endpoint"]} --command default --private --wait', table=False)
    assert f'endpoint "{drec["endpoint"]}" is already in use' in str(excinfo.value)
    assert not any(r['name'] == dname for r in user_session.deployment_list())


def test_deploy_collaborators(user_session, cli_deployment):
    uname = 'tooltest2'
    prec, drec = cli_deployment
    clist = _cmd(f'deployment collaborator list {drec["id"]}')
    assert len(clist) == 0
    clist = _cmd(f'deployment collaborator add {drec["id"]} {uname}')
    assert len(clist) == 1
    clist = _cmd(f'deployment collaborator add {drec["id"]} everyone --group')
    assert len(clist) == 2
    assert all(c['id'] == uname and c['type'] == 'user' or
               c['id'] == 'everyone' and c['type'] == 'group'
               for c in clist)
    clist = _cmd(f'deployment collaborator remove {drec["id"]} {uname} everyone')
    assert len(clist) == 0
    with pytest.raises(CMDException) as excinfo:
        clist = _cmd(f'deployment collaborator remove {drec["id"]} {uname}')
    assert f'Collaborator(s) not found: {uname}' in str(excinfo.value)


def test_deploy_broken(user_session, cli_deployment):
    prec, drec = cli_deployment
    dname = drec['name'] + '-broken'
    with pytest.raises(CMDException) as excinfo:
        _cmd(f'project deploy {prec["id"]} --name {dname} --command broken --private --stop-on-error', table=False)
    assert 'Error completing deployment start: App failed to run' in str(excinfo.value)
    assert not any(r['name'] == dname for r in _cmd('deployment list'))


def test_job_run1(user_session):
    uname = user_session.username
    _cmd(f'job create {uname}/testproj3 --name testjob1 --command run --run --wait')
    jrecs = _cmd('job list')
    assert len(jrecs) == 1, jrecs
    rrecs = _cmd('run list')
    assert len(rrecs) == 1, rrecs
    ldata1 = _cmd(f'run log {rrecs[0]["id"]}', table=False)
    assert ldata1.strip().endswith('Hello Anaconda Enterprise!'), repr(ldata1)
    _cmd(f'job create {uname}/testproj3 --name testjob1 --make-unique --command run --run --wait')
    jrecs = _cmd('job list')
    assert len(jrecs) == 2, jrecs
    rrecs = _cmd('run list')
    assert len(rrecs) == 2, rrecs
    for rrec in rrecs:
        _cmd(f'run delete {rrec["id"]} --yes', table=False)
    for jrec in jrecs:
        _cmd(f'job delete {jrec["id"]} --yes', table=False)
    assert not _cmd('job list')
    assert not _cmd('run list')


def test_job_run2(user_session):
    uname = user_session.username
    # Test cleanup mode and variables in jobs
    variables = {'INTEGRATION_TEST_KEY_1': 'value1', 'INTEGRATION_TEST_KEY_2': 'value2'}
    vars = ' '.join(f'--variable {k}={v}' for k, v in variables.items())
    _cmd(f'project run {uname}/testproj3 --command run_with_env_vars --name testjob2 {vars}')
    # The job record should have already been deleted
    assert not _cmd('job list')
    rrecs = _cmd('run list')
    assert len(rrecs) == 1, rrecs
    ldata2 = _cmd(f'run log {rrecs[0]["id"]}', table=False)
    # Confirm that the environment variables were passed through
    outvars = dict(line.strip().replace(' ', '').split(':', 1)
                   for line in ldata2.splitlines()
                   if line.startswith('INTEGRATION_TEST_KEY_'))
    assert variables == outvars, outvars
    _cmd(f'run delete {rrecs[0]["id"]} --yes', table=False)
    assert not _cmd('run list')


def test_login_time(admin_session, user_session):
    # The current login time should be before the present
    now = datetime.utcnow()
    _cmd('project list')
    user_list = _cmd('user list')
    urec = next((r for r in user_list if r['username'] == user_session.username), None)
    assert urec is not None
    ltm1 = datetime.strptime(urec['lastLogin'], "%Y-%m-%d %H:%M:%S.%f")
    assert ltm1 < now
    # No more testing here, because we want to preserve the existing sessions
