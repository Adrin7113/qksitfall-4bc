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
  fixture=JSON.parse(readFileSync(join(here,'fixture.json'),'utf8'));
  console.log('Using committed Python-exported fixture; set PARKING_PYTHON to refresh.');
}
const model=readFileSync(join(here,'model.mjs'),'utf8').replaceAll('export ','');
const script=['motion.js','circuit.js','app.js'].map(name=>readFileSync(join(here,name),'utf8')).join('\n');
const css=readFileSync(join(here,'style.css'),'utf8');
let html=readFileSync(join(here,'template.html'),'utf8')
  .replace('<!--STYLE-->',()=>`<style>${ISO_CSS}\n${css}</style>`)
  .replace('<!--FIGURE-->',()=>buildFigure())
  .replace('<!--SCRIPT-->',()=>`<script>const FIXTURE=${JSON.stringify(fixture)};const PROJECTION=${JSON.stringify(projection)};const SCENE=${JSON.stringify(SCENE)};const PROJECTION_BASIS=${JSON.stringify(projectionBasis)};${model}\n${script}</script>`);
if(process.argv.includes('--light'))html=html.replace('data-theme="dark"','data-theme="light"');
mkdirSync(join(here,'dist'),{recursive:true});
writeFileSync(join(here,'dist',process.argv.includes('--light')?'index-light.html':'index.html'),html);
console.log(`Built ${process.argv.includes('--light')?'dist/index-light.html':'dist/index.html'} · ${fixture.options.length} Python-generated booking options · ${Math.round(Buffer.byteLength(html)/1024)} kB`);

if(existsSync(join(here,'vendor/fonts')))cpSync(join(here,'vendor/fonts'),join(here,'dist/assets/fonts'),{recursive:true});
