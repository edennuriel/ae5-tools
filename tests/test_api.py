import tempfile
import requests
import time
import pytest
import os
import tarfile
import glob
import uuid

from datetime import datetime

from ae5_tools.api import AEUserSession, AEUnexpectedResponseError


def test_project_info(user_session, project_list):
    for rec0 in project_list:
        id = rec0['id']
        pair = '{}/{}'.format(rec0['owner'], rec0['name'])
        rec1 = user_session.project_info(id, collaborators=True)
        rec2 = user_session.project_info(pair)
        rec3 = user_session.project_info(f'{pair}/{id}')
        assert all(rec0[k] == v for k, v in rec2.items())
        assert all(rec1[k] == v for k, v in rec2.items())
        assert rec2 == rec3


def test_project_collaborators(user_session, project_list):
    for rec0 in project_list:
        collabs = rec0['collaborators']
        collabs = set(collabs.split(', ')) if collabs else set()
        collab2 = user_session.project_collaborator_list(rec0['id'])
        collab3 = set(c['id'] for c in collab2)
        assert collabs == collab3, collab2


def test_project_activity(user_session, project_list):
    for rec0 in project_list:
        activity = user_session.project_activity(f'{rec0["owner"]}/{rec0["name"]}', limit=-1)
        assert activity[-1]['status'] == 'created'
        assert activity[-1]['done']
        assert activity[-1]['owner'] == rec0['owner']


@pytest.fixture(scope='module')
def downloaded_project(user_session):
    uname = user_session.username
    with tempfile.TemporaryDirectory() as tempd:
        fname = os.path.join(tempd, 'blob.tar.gz')
        fname2 = os.path.join(tempd, 'blob2.tar.gz')
        user_session.project_download(f'{uname}/testproj1', filename=fname)
        with tarfile.open(fname, 'r') as tf:
            tf.extractall(path=tempd)
        dnames = glob.glob(os.path.join(tempd, '*', 'anaconda-project.yml'))
        assert len(dnames) == 1
        dname = os.path.dirname(dnames[0])
        yield fname, fname2, dname
    for r in user_session.session_list():
        if r['owner'] == uname and r['name'].startswith('test_upload'):
            user_session.session_stop(r)
    for r in user_session.project_list():
        if r['owner'] == uname and r['name'].startswith('test_upload'):
            user_session.project_delete(r)
    assert not any(r['owner'] == uname and r['name'].startswith('test_upload')
                   for r in user_session.project_list())


def test_project_download(downloaded_project):
    pass


def test_project_upload(user_session, downloaded_project):
    fname, fname2, dname = downloaded_project
    user_session.project_upload(fname, 'test_upload1', '1.2.3', wait=True)
    rrec = user_session.revision_list('test_upload1')
    assert len(rrec) == 1
    assert rrec[0]['name'] == '1.2.3'
    user_session.project_download('test_upload1:1.2.3', filename=fname2)


def test_project_upload_as_directory(user_session, downloaded_project):
    fname, fname2, dname = downloaded_project
    user_session.project_upload(dname, 'test_upload2', '1.3.4', wait=True)
    rrec = user_session.revision_list('test_upload2')
    assert len(rrec) == 1
    assert rrec[0]['name'] == '1.3.4'
    user_session.project_download('test_upload2:1.3.4', filename=fname2)


def test_project_create_from_sample(user_session):
    uname = user_session.username
    cname = 'nlp_api'
    pname = 'testclone'
    rrec = user_session.sample_clone(cname, name=pname, wait=True)
    user_session.project_delete(rrec['id'])


def test_job_run1(user_session):
    uname = user_session.username
    user_session.job_create(f'{uname}/testproj3', name='testjob1', command='run', run=True, wait=True)
    jrecs = user_session.job_list()
    assert len(jrecs) == 1, jrecs
    rrecs = user_session.run_list()
    assert len(rrecs) == 1, rrecs
    ldata1 = user_session.run_log(rrecs[0]['id'], format='text')
    assert ldata1.endswith('Hello Anaconda Enterprise!\n'), repr(ldata1)
    user_session.job_create(f'{uname}/testproj3', name='testjob1', command='run', make_unique=True, run=True, wait=True)
    jrecs = user_session.job_list()
    assert len(jrecs) == 2, jrecs
    rrecs = user_session.run_list()
    assert len(rrecs) == 2, rrecs
    for rrec in rrecs:
        user_session.run_delete(rrec['id'])
    for jrec in jrecs:
        user_session.job_delete(jrec['id'])
    assert not user_session.job_list()
    assert not user_session.run_list()


def test_job_run2(user_session):
    uname = user_session.username
    # Test cleanup mode and variables in jobs
    variables = {'INTEGRATION_TEST_KEY_1': 'value1', 'INTEGRATION_TEST_KEY_2': 'value2'}
    user_session.job_create(f'{uname}/testproj3', name='testjob2', command='run_with_env_vars',
                            variables=variables, run=True, wait=True, cleanup=True)
    # The job record should have already been deleted
    assert not user_session.job_list()
    rrecs = user_session.run_list()
    assert len(rrecs) == 1, rrecs
    ldata2 = user_session.run_log(rrecs[0]['id'], format='text')
    # Confirm that the environment variables were passed through
    outvars = dict(line.strip().replace(' ', '').split(':', 1)
                   for line in ldata2.splitlines()
                   if line.startswith('INTEGRATION_TEST_KEY_'))
    assert variables == outvars, outvars
    user_session.run_delete(rrecs[0]['id'])
    assert not user_session.run_list()


@pytest.fixture(scope='module')
def api_session(user_session):
    uname = user_session.username
    pname = 'testproj3'
    user_session.session_start(f'{uname}/{pname}', wait=True)
    srecs = [r for r in user_session.session_list()
             if r['owner'] == uname and r['name'] == pname]
    assert len(srecs) == 1, srecs
    yield srecs[0]['id'], pname
    user_session.session_stop(srecs[0]['id'])
    srecs = [r for r in user_session.session_list()
             if r['owner'] == uname and r['name'] == dname
             or r['id'] == srecs[0]['id']]
    assert len(srecs) == 0, srecs


def test_session(user_session, api_session):
    id, pname = api_session
    endpoint = id.rsplit("-", 1)[-1]
    sdata = user_session._get('/', subdomain=endpoint, format='text')
    assert 'Jupyter Notebook requires JavaScript.' in sdata, sdata


def test_session_branches(user_session, api_session):
    id, pname = api_session
    branches = user_session.session_branches(id, format='json')
    bdict = {r['branch']: r['sha1'] for r in branches}
    assert set(bdict) == {'local', 'origin/local', 'master'}, branches
    assert bdict['local'] == bdict['master'], branches


def test_session_before_changes(user_session, api_session):
    id, pname = api_session
    changes1 = user_session.session_changes(id, format='json')
    assert changes1 == [], changes1
    changes2 = user_session.session_changes(id, master=True, format='json')
    assert changes2 == [], changes2


@pytest.fixture(scope='module')
def api_deployment(user_session):
    uname = user_session.username
    dname = 'testdeploy'
    ename = 'testendpoint'
    user_session.deployment_start(f'{uname}/testproj3', name=dname, endpoint=ename,
                                  command='default', public=False, wait=True)
    drecs = [r for r in user_session.deployment_list()
             if r['owner'] == uname and r['name'] == dname]
    assert len(drecs) == 1, drecs
    yield drecs[0]['id'], ename
    user_session.deployment_stop(drecs[0]['id'])
    drecs = [r for r in user_session.deployment_list()
             if r['owner'] == uname and r['name'] == dname
             or r['id'] == drecs[0]['id']]
    assert len(drecs) == 0, drecs


def test_deploy(user_session, api_deployment):
    id, ename = api_deployment
    for attempt in range(3):
        try:
            ldata = user_session._get('/', subdomain=ename, format='text')
            break
        except AEUnexpectedResponseError:
            time.sleep(attempt * 5)
            pass
    else:
        raise RuntimeError("Could not get the endpoint to respond")
    assert ldata.strip() == 'Hello Anaconda Enterprise!', ldata


def test_deploy_token(user_session, api_deployment):
    id, ename = api_deployment
    token = user_session.deployment_token(id)
    resp = requests.get(f'https://{ename}.' + user_session.hostname,
                        headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.text.strip() == 'Hello Anaconda Enterprise!', resp.text


def test_deploy_logs(user_session, api_deployment):
    id, ename = api_deployment
    app_prefix = 'anaconda-app-' + id.rsplit("-", 1)[-1] + '-'
    logs = user_session.deployment_logs(id, format='json')
    assert set(logs) == {'app', 'events', 'name', 'proxy'}, logs
    assert logs['name'].startswith(app_prefix), logs['name']
    assert 'The project is ready to run commands.' in logs['app'], logs['app']
    assert app_prefix in logs['events'], logs['events']
    assert 'App Proxy is fully operational!' in logs['proxy'], logs['proxy']


def test_deploy_duplicate(user_session, api_deployment):
    uname = user_session.username
    id, ename = api_deployment
    dname = 'testdeploy2'
    with pytest.raises(RuntimeError) as excinfo:
        user_session.deployment_start(f'{uname}/testproj3', name=dname, endpoint=ename,
                                      command='default', public=False, wait=True)
    assert f'endpoint "{ename}" is already in use' in str(excinfo.value)
    drecs = [r for r in user_session.deployment_list()
             if r['owner'] == uname and r['name'] == dname]
    assert len(drecs) == 0, drecs


def test_deploy_broken(user_session):
    uname = user_session.username
    dname = 'testbroken'
    with pytest.raises(RuntimeError) as excinfo:
        user_session.deployment_start(f'{uname}/testproj3', name=dname,
                                      command='broken', public=False,
                                      stop_on_error=True)
    assert 'Error completing deployment start: App failed to run' in str(excinfo.value)
    drecs = [r for r in user_session.deployment_list()
             if r['owner'] == uname and r['name'] == dname]
    assert len(drecs) == 0, drecs


def test_login_time(admin_session, user_session):
    # The current session should already be authenticated
    now = datetime.utcnow()
    plist0 = user_session.project_list()
    user_list = admin_session.user_list()
    urec = next((r for r in user_list if r['username'] == user_session.username), None)
    assert urec is not None
    ltm1 = datetime.fromtimestamp(urec['lastLogin'] / 1000.0)
    assert ltm1 < now

    # Create new login session. This should change lastLogin
    password = os.environ.get('AE5_PASSWORD')
    user_sess2 = AEUserSession(user_session.hostname, user_session.username, password, persist=False)
    plist1 = user_sess2.project_list()
    urec = admin_session.user_info(urec['id'])
    ltm2 = datetime.fromtimestamp(urec['lastLogin'] / 1000.0)
    assert ltm2 > ltm1
    user_sess2.disconnect()
    assert plist1 == plist0

    # Create new impersonation session. This should not change lastLogin
    user_sess3 = AEUserSession(admin_session.hostname, user_session.username, admin_session, persist=False)
    plist2 = user_sess3.project_list()
    urec = admin_session.user_info(urec['id'])
    ltm3 = datetime.fromtimestamp(urec['lastLogin'] / 1000.0)
    assert ltm3 == ltm2
    user_sess3.disconnect()
    # Confirm the impersonation worked by checking the project lists are the same
    assert plist2 == plist0

    # Access the original login session. It should not reauthenticate
    plist3 = user_session.project_list()
    urec = admin_session.user_info(urec['id'])
    ltm4 = datetime.fromtimestamp(urec['lastLogin'] / 1000.0)
    assert ltm4 == ltm3
    assert plist3 == plist0
