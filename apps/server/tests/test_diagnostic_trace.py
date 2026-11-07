import json

from test_operator_console import TOKEN, client_for

from apris_server.diagnostic_trace import DiagnosticTrace
from apris_server.operator_console import create_console


def test_trace_is_bounded_and_copies_entries_and_marks_loss():
    trace = DiagnosticTrace(max_entries=2, max_bytes=1000, clock=lambda: 12.0)
    detail = {'reason': 'original'}
    trace.record('first', {'runEpoch': 'old'}, detail)
    detail['reason'] = 'mutated'
    assert trace.export()['entries'][0]['detail']['reason'] == 'original'
    trace.record('second', {'runEpoch': 'new'})
    trace.record('third', {})
    export = trace.export()
    assert export['dropped'] == 1 and not export['complete']
    assert [e['cursor'] for e in export['entries']] == [2, 3]
    export['entries'][0]['context']['runEpoch'] = 'tampered'
    assert trace.export()['entries'][0]['context']['runEpoch'] == 'new'
    trace.record('oversize', {}, {'text': 'x' * 2000})
    trace.record('invalid', {}, {'nan': float('nan')})
    assert trace.export()['dropped'] == 3
    assert trace.bytes <= 1000
    json.dumps(trace.export(), allow_nan=False)


def test_trace_byte_limit_and_sampling():
    now = [0.0]
    trace = DiagnosticTrace(max_entries=100, max_bytes=500, clock=lambda: now[0])
    assert trace.sample_due()
    assert not trace.sample_due()
    now[0] = .5
    assert trace.sample_due()
    for _ in range(20):
        trace.record('sample', {}, {'padding': 'x' * 100})
    assert trace.bytes <= 500
    assert trace.export()['dropped'] > 0


def test_trace_export_is_authenticated_observational_and_not_replayable():
    with client_for(create_console(TOKEN)) as client:
        port = client.app.state.port
        port.record_trace('test', {'reason': 'fixture'})
        before = (port.session, port.operator_id, port.inhibited, port.guard_id)
        response = client.get('/api/trace')
        assert response.status_code == 200
        assert 'attachment' in response.headers['content-disposition']
        assert response.json()['entries'][-1]['kind'] == 'test'
        assert TOKEN not in response.text
        assert (port.session, port.operator_id, port.inhibited, port.guard_id) == before
        assert client.get('/api/trace', headers={'Authorization': ''}).status_code == 401
        assert client.post('/api/trace', json=response.json()).status_code == 405


def test_recording_does_not_evaluate_estimator_or_change_guard():
    from types import SimpleNamespace

    with client_for(create_console(TOKEN)) as client:
        port = client.app.state.port
        def forbidden():
            raise AssertionError('diagnostics evaluated estimator')
        port.localization = SimpleNamespace(
            diagnostic_snapshot={'sampleTime': 1}, blocked=True, reason='fixture', epoch='loc',
            estimator=SimpleNamespace(snapshot=forbidden))
        try:
            port.record_trace('inspect')
            context = port.trace.export()['entries'][-1]['context']
            assert context['localization'] == {'sampleTime': 1}
            assert context['localizationGate']['reason'] == 'fixture'
        finally:
            port.localization = None


def test_late_motion_terminal_keeps_original_run_epoch():
    with client_for(create_console(TOKEN)) as client:
        port = client.app.state.port
        assert port.session is None
        port.emit(dict(kind='terminal', protocolVersion=1, connectionEpoch='old-epoch',
                       runId='old-run', outcome='interrupted'))
        entry = port.trace.export()['entries'][-1]
        assert entry['context']['runEpoch'] == 'old-epoch'
        assert entry['context']['runId'] == 'old-run'
        assert entry['context']['route'] is None
