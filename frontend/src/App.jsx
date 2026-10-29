import {useState,useEffect,useRef} from 'react'
const API_BASE=(import.meta.env.VITE_API_URL||'').replace(/\/+$/,'')
const api=async(p,o={})=>{const t=localStorage.token;const r=await fetch(API_BASE+'/api'+p,{...o,headers:{...(t&&{Authorization:'Bearer '+t}),...o.headers}});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||'Something went wrong. Please try again.');return j}
const post=(p,b)=>api(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})
function Auth({done}){const[m,setM]=useState('login');const[f,setF]=useState({name:'',email:'',password:''});const[e,setE]=useState('')
const go=async ev=>{ev.preventDefault();try{const r=await post('/auth/'+m,f);localStorage.token=r.token;done()}catch(x){setE(x.message)}}
return <main><h1>CaneGuard AI</h1><p>Sugarcane leaf disease detection with a CNN.</p><form onSubmit={go}>
{m==='register'&&<label>Full name<input value={f.name} onChange={x=>setF({...f,name:x.target.value})} required/></label>}
<label>Email<input type="email" value={f.email} onChange={x=>setF({...f,email:x.target.value})} required/></label>
<label>Password<input type="password" minLength={8} value={f.password} onChange={x=>setF({...f,password:x.target.value})} required/></label>
{e&&<p className="err" role="alert">{e}</p>}<button className="btn">{m==='login'?'Log in':'Create account'}</button>
<p><button type="button" onClick={()=>setM(m==='login'?'register':'login')}>{m==='login'?'Need an account? Register':'Have an account? Log in'}</button></p></form></main>}
function Result({r}){const i=r.info;return <div className="card"><b>{r.filename}</b>
{r.status==='success'?<><h3>{r.prediction}</h3><div className="bar"><i style={{width:r.confidence*100+'%'}}/></div><small>Confidence {(r.confidence*100).toFixed(1)}%</small><p>{i?.description}</p>
{['symptoms','management','prevention'].map(k=>i?.[k]?.length?<div key={k}><b>{k}</b><ul>{i[k].map(s=><li key={s}>{s}</li>)}</ul></div>:null)}<small>{i?.when_to_seek_help}</small></>
:<p className="err">{r.status==='uncertain'?'Unable to make a reliable prediction.':'Image not suitable for analysis.'} {r.message}</p>}</div>}
function Analyze(){const[files,setF]=useState([]);const[res,setR]=useState([]);const[busy,setB]=useState(false);const[err,setE]=useState('');const[cam,setCam]=useState(false);const v=useRef()
const add=l=>setF(f=>[...f,...l]);const rm=i=>setF(f=>f.filter((_,j)=>j!==i))
const start=async()=>{try{const s=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}}});v.current.srcObject=s;setCam(true)}catch{setE('Camera permission denied or unavailable.')}}
const stop=()=>{v.current?.srcObject?.getTracks().forEach(t=>t.stop());setCam(false)}
const snap=()=>{const c=document.createElement('canvas');c.width=v.current.videoWidth;c.height=v.current.videoHeight;c.getContext('2d').drawImage(v.current,0,0);c.toBlob(b=>add([new File([b],'camera.jpg',{type:'image/jpeg'})]),'image/jpeg',.92);stop()}
const run=async()=>{setB(true);setE('');const fd=new FormData();files.forEach(f=>fd.append('files',f));try{setR(await api('/analyze/batch',{method:'POST',body:fd}))}catch(x){setE(x.message)}setB(false)}
useEffect(()=>stop,[])
return <main><h2>Analyze sugarcane leaf</h2><label>Upload images (JPG, PNG, WEBP)<input type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={e=>add([...e.target.files])}/></label>
<button className="btn" onClick={cam?snap:start}>{cam?'Capture image':'Start camera'}</button> {cam&&<button onClick={stop}>Stop camera</button>}
<video ref={v} autoPlay playsInline muted hidden={!cam}/>
<div className="grid">{files.map((f,i)=><div className="card" key={i}><img src={URL.createObjectURL(f)} alt={f.name}/><small>{f.name}</small><br/><button onClick={()=>rm(i)}>Remove</button></div>)}</div>
{files.length>0&&<p><button className="btn" onClick={run} disabled={busy}>{busy?'Validating, running CNN, calculating confidence…':`Analyze ${files.length} image(s)`}</button></p>}
{err&&<p className="err" role="alert">{err}</p>}<div className="grid">{res.map((r,i)=><Result key={i} r={r}/>)}</div>
<p><small>Preliminary screening only; not a substitute for professional agricultural advice.</small></p></main>}
function History(){const[h,setH]=useState([]);useEffect(()=>{api('/analyses').then(setH)},[]);return <main><h2>Analysis history</h2>{!h.length&&<p>No analyses yet.</p>}
<div className="grid">{h.map(a=><div className="card" key={a.id}><b>{a.filename}</b><br/>{a.status}{a.prediction&&` — ${a.prediction}`}{a.confidence!=null&&` (${(a.confidence*100).toFixed(1)}%)`}<br/><small>{a.created_at}</small></div>)}</div></main>}
function Library(){const[d,setD]=useState({});const[m,setM]=useState(null);useEffect(()=>{api('/diseases').then(setD);api('/model/info').then(setM)},[])
return <main><h2>Disease library</h2><div className="grid">{Object.entries(d).map(([k,v])=><div className="card" key={k}><h3>{k}</h3><p>{v.description||'Information not available.'}</p>{v.symptoms&&<ul>{v.symptoms.map(s=><li key={s}>{s}</li>)}</ul>}</div>)}</div>
{m&&<><h3>Model</h3><p>Loaded: {String(m.loaded)}. Confidence threshold: {m.confidence_threshold}. Metrics: {typeof m.metrics==='string'?m.metrics:`test images ${m.metrics.test_images}, accuracy ${(m.metrics.report.accuracy*100).toFixed(1)}%`}</p></>}</main>}
export default function App(){const[auth,setA]=useState(!!localStorage.token);const[p,setP]=useState('analyze')
if(!auth)return <Auth done={()=>setA(true)}/>
return <><nav><b>CaneGuard AI</b>{['analyze','history','diseases'].map(x=><button key={x} onClick={()=>setP(x)}>{x}</button>)}<button onClick={()=>{localStorage.clear();setA(false)}}>Log out</button></nav>
{p==='analyze'?<Analyze/>:p==='history'?<History/>:<Library/>}</>}
