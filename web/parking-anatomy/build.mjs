import {readFileSync,writeFileSync,mkdirSync,cpSync,existsSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {buildFigure,projection,SCENE,projectionBasis} from './geometry.mjs';
import {ISO_CSS} from './vendor/iso-kit.mjs';

const here=dirname(fileURLToPath(import.meta.url));
let fixture;
try {
  const python=process.env.PARKING_PYTHON || join(here,'../../.venv/bin/python');
  fixture=JSON.parse(execFileSync(python,[join(here,'export_fixture.py')],{encoding:'utf8'}));
  writeFileSync(join(here,'fixture.json'),JSON.stringify(fixture,null,2)+'\n');
}catch(error){
  if(process.env.PARKING_REQUIRE_PYTHON==='1'||error.code!=='ENOENT')throw error;
  fixture=JSON.parse(readFileSync(join(here,'fixture.json'),'utf8'));
  console.log('Using committed Python-exported fixture; set PARKING_PYTHON to refresh.');
}
if(!fixture.shared_power)throw new Error('Missing shared-power export. Refresh with PARKING_PYTHON and PARKING_SOURCE_ROOT.');
const report=JSON.parse(readFileSync(join(here,'benchmark.json'),'utf8'));
if(JSON.stringify(report)!==JSON.stringify(fixture.benchmark))throw new Error('Stale benchmark export: refresh Python fixture.');
for(const [name,hash] of Object.entries(report.source_hashes)){
 if(fixture.source_hashes[name]!==hash)throw new Error('Benchmark source hash mismatch: '+name);
}
const model=readFileSync(join(here,'model.mjs'),'utf8').replaceAll('export ','');
const sharedModel=readFileSync(join(here,'shared-model.mjs'),'utf8').replaceAll('export ','');
const benchmarkModel=readFileSync(join(here,'benchmark-model.mjs'),'utf8').replaceAll('export ','');
const script=['motion.js','circuit.js','equations.js','shared-power.js','app.js','presenter.js','benchmark.js'].map(name=>readFileSync(join(here,name),'utf8')).join('\n');
const css=readFileSync(join(here,'style.css'),'utf8');
let html=readFileSync(join(here,'template.html'),'utf8')
  .replace('<!--STYLE-->',()=>`<style>${ISO_CSS}\n${css}</style>`)
  .replace('<!--FIGURE-->',()=>buildFigure())
  .replace('<!--SCRIPT-->',()=>`<script>const FIXTURE=${JSON.stringify(fixture)};const PROJECTION=${JSON.stringify(projection)};const SCENE=${JSON.stringify(SCENE)};const PROJECTION_BASIS=${JSON.stringify(projectionBasis)};${model}\n${sharedModel}\n${benchmarkModel}\n${script}</script>`);
if(process.argv.includes('--light'))html=html.replace('data-theme="dark"','data-theme="light"');
mkdirSync(join(here,'dist'),{recursive:true});
writeFileSync(join(here,'dist',process.argv.includes('--light')?'index-light.html':'index.html'),html);
console.log(`Built ${process.argv.includes('--light')?'dist/index-light.html':'dist/index.html'} · ${fixture.options.length} Python-generated booking options · ${Math.round(Buffer.byteLength(html)/1024)} kB`);

if(existsSync(join(here,'vendor/fonts')))cpSync(join(here,'vendor/fonts'),join(here,'dist/assets/fonts'),{recursive:true});
