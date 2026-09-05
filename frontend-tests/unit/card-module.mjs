/** Load complete delivered modules; only the browser/Lit boundary is simulated. */
import {readFile} from 'node:fs/promises';
import {createContext, SourceTextModule, SyntheticModule} from 'node:vm';
const root = new URL('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/', import.meta.url);
const registry = new Map();
const html = (strings, ...values) => strings.reduce((text, part, i) => text + part + (values[i] == null || values[i] === false ? '' : Array.isArray(values[i]) ? values[i].join('') : values[i]), '');
class Element extends EventTarget {
  constructor(){super();this.dataset={};this.style={setProperty(){}};}
  requestUpdate(){}
  setAttribute(){}
  removeAttribute(){}
  getAttribute(){return null;}
  hasAttribute(){return false;}
  connectedCallback(){}
  disconnectedCallback(){}
}
const document={querySelector:()=>null,head:{appendChild(){}},createElement:()=>({setAttribute(){}})};
export const browserWindow = Object.assign(new EventTarget(), {customCards:[], setTimeout:(...args)=>setTimeout(...args), clearTimeout:(...args)=>clearTimeout(...args)});
const context=createContext({console,URL,Intl,Date,Map,Set,WeakMap,WeakSet,EventTarget,Event,CustomEvent,HTMLElement:Element,document,navigator:{language:'en-GB'},window:browserWindow,customElements:{get:key=>registry.get(key),define:(key,value)=>registry.set(key,value)},setTimeout,clearTimeout,setInterval,clearInterval,requestAnimationFrame:()=>0,cancelAnimationFrame(){},ResizeObserver:class{observe(){}disconnect(){}}});
const modules=new Map();
async function load(url){
  url=new URL(url);url.search='';const key=url.href;
  if(!modules.has(key))modules.set(key,(async()=>{
    let module;
    if(url.pathname.endsWith('/f1-lit-3.3.2.js'))module=new SyntheticModule(['LitElement','html','css','svg'],function(){this.setExport('LitElement',Element);this.setExport('html',html);this.setExport('css',html);this.setExport('svg',html);},{context});
    else module=new SourceTextModule(await readFile(url,'utf8'),{context,identifier:key,initializeImportMeta:meta=>{meta.url=key;},importModuleDynamically:specifier=>load(new URL(specifier,url))});
    await module.link(specifier=>load(new URL(specifier,url)));
    await module.evaluate();return module;
  })());
  return modules.get(key);
}
await load(new URL('f1-sensor-live-data-card.js',root));
export function card(type, config={}) {
  const Class=registry.get(type);if(!Class)throw new Error(`Unregistered card ${type}`);
  const result=new Class();result.config=config;result.hass={states:{},locale:{language:'en-GB',time_format:'24',time_zone:'UTC'},config:{time_zone:'UTC'}};
  return result;
}
