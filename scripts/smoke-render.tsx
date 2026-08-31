// Smoke test render SSR utk komponen MAA — menangkap crash render deterministik
// (mis. crash saat upload gambar). Jalankan: bun scripts/smoke-render.tsx
import { renderToString } from 'react-dom/server';
import { MessageList } from '../src/components/maa/message-list';
import { Composer, type PendingUpload } from '../src/components/maa/composer';
import { TodoPanel } from '../src/components/maa/todo-panel';
import { TracePanel } from '../src/components/maa/trace-panel';

const notify = () => {};
const noop = () => {};

let failures = 0;

function render(name: string, el: React.ReactElement, allowEmpty = false) {
  try {
    const html = renderToString(el);
    if (!html || html.length < 10) {
      if (!allowEmpty) throw new Error('output kosong');
    }
    console.log(`PASS  ${name}`);
  } catch (e) {
    failures++;
    console.log(`FAIL  ${name}: ${(e as Error).message}`);
  }
}

// ---------- MessageList: variasi lampiran ----------
const baseMsg = { role: 'user', text: 'halo', ts: 1 };

render('ML: atts image (kind image + url)', (
  <MessageList
    messages={[
      { ...baseMsg, atts: [{ name: 'foto.png', kind: 'image', size: 1234, url: 'https://x/y' }] },
      { role: 'assistant', text: 'jawaban', ts: 2, model: 'nova-micro' },
    ]}
    processing={false}
    onResendEdit={noop}
    notify={notify}
    autoRoute={{ chosen: 'AUTO', model: 'nova-micro' }}
    attachments={[]}
  />
));

render('ML: atts BUKAN array (string)', (
  <MessageList
    messages={[{ ...baseMsg, atts: 'rusak' as unknown as never[] }]}
    processing={false}
    onResendEdit={noop}
    notify={notify}
  />
));

render('ML: atts BUKAN array (object)', (
  <MessageList
    messages={[{ ...baseMsg, atts: { name: 'x' } as unknown as never[] }]}
    processing={false}
    onResendEdit={noop}
    notify={notify}
  />
));

render('ML: atts null/undefined item', (
  <MessageList
    messages={[{ ...baseMsg, atts: [null as unknown as { name: string }] }]}
    processing={false}
    onResendEdit={noop}
    notify={notify}
  />
));

render('ML: messages bukan array', (
  <MessageList
    messages={'rusak' as unknown as never[]}
    processing={false}
    onResendEdit={noop}
    notify={notify}
  />
));

render('ML: versions rusak', (
  <MessageList
    messages={[{ role: 'assistant', text: 'a', ts: 1, versions: [{ text: 'x', ts: 0 }, null as unknown as { text: string; ts: number }] }]}
    processing={false}
    onResendEdit={noop}
    notify={notify}
  />
));

render('ML: deck + webapp artefak', (
  <MessageList
    messages={[
      {
        role: 'assistant', text: 'deck jadi', ts: 1,
        atts: [{ kind: 'deck', name: 'Deck', url: 'https://x', slides: 5 },
               { kind: 'webapp', name: 'App', url: 'https://x', files: 2 }],
      },
    ]}
    processing={false}
    onResendEdit={noop}
    notify={notify}
  />
));

render('ML: teks markdown aneh', (
  <MessageList
    messages={[{ role: 'assistant', text: '| a | b |\n![x]()\n``` unclosed\n**bold', ts: 1 }]}
    processing={false}
    onResendEdit={noop}
    notify={notify}
  />
));

// ---------- Composer: uploads ----------
const uploads: PendingUpload[] = [
  { key: 'k1', name: 'a.png', size: 123, contentType: 'image/png', progress: 100 },
  { key: 'k2', name: 'b.csv', size: 456, contentType: 'text/csv', progress: 50 },
  { key: 'k3', name: 'c.pdf', size: 789, contentType: 'application/pdf', progress: 0, error: 'S3 403' },
];

render('Composer: uploads campuran', (
  <Composer
    mode="AUTO"
    onModeChange={noop}
    agentMode="STANDARD"
    onAgentModeChange={noop}
    manualModel=""
    onManualModelChange={noop}
    models={[]}
    onSend={noop}
    uploads={uploads}
    onRemoveUpload={noop}
  />
));

render('Composer: uploads undefined', (
  <Composer
    mode="MANUAL"
    onModeChange={noop}
    agentMode="MULTI"
    onAgentModeChange={noop}
    manualModel=""
    onManualModelChange={noop}
    models={[]}
    onSend={noop}
  />
));

// ---------- TodoPanel ----------
render('Todo: normal', <TodoPanel todos={[{ content: 'a', status: 'in_progress' }, { content: 'b', status: 'completed' }]} />);
render('Todo: null', <TodoPanel todos={null} />, true);
render('Todo: status aneh', <TodoPanel todos={[{ content: 'a', status: 'apa-aja' }, { content: 'b', status: '' }]} />);

// ---------- TracePanel ----------
render('Trace: event tak dikenal', (
  <TracePanel
    events={[
      { ts: '1', type: 'event_misterius_baru', content: 'x' },
      { ts: '2', type: '', content: '' },
      { ts: 'abc', type: 'upload', content: 'gambar diproses' },
    ]}
    processing
  />
));

console.log(failures === 0 ? '\nSEMUA PASS' : `\n${failures} FAIL`);
process.exit(failures === 0 ? 0 : 1);
