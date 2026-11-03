"use strict";
const tg=window.Telegram?.WebApp;
const el=id=>document.getElementById(id);
let token=sessionStorage.getItem("zei-session")||"", state={}, busy=false, choice="";
const labels={forcesubs:"ForceSubs",payment:"Payment",userbot:"Userbot"};
const descriptions={forcesubs:"Bagikan konten dengan akses channel.",payment:"Ruang penjualan akses milikmu.",userbot:"Kendali pribadi dari akun Telegrammu."};
function node(tag,text,cls){const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;}
function field(id,label,type="text",hint=""){
 const labelNode=node("label",label);labelNode.htmlFor=id;el("fields").append(labelNode);
 const wrap=node("div",null,type==="password"?"secret":"");const input=node("input");
 input.id=id;input.name=id;input.type=type;input.required=true;input.autocomplete="off";input.spellcheck=false;
 if(id==="api_id"||id==="code")input.inputMode="numeric";
 if(id==="phone"){input.type="tel";input.placeholder="+628123456789";}
 if(id==="code"){input.autocomplete="one-time-code";input.maxLength=8;}
 if(id==="api_hash")input.maxLength=32;
 if(id==="password")input.maxLength=256;
 wrap.append(input);
 if(type==="password"){const eye=node("button","Lihat","eye");eye.type="button";eye.setAttribute("aria-label","Tampilkan "+label);eye.onclick=()=>{input.type=input.type==="password"?"text":"password";eye.textContent=input.type==="password"?"Lihat":"Tutup";};wrap.append(eye);}
 el("fields").append(wrap);if(hint)el("fields").append(node("p",hint,"hint"));
}
function link(text,url){const a=node("a",text);a.href=url;a.target="_blank";a.rel="noopener noreferrer";return a;}
async function sharePhone(button){
 if(busy)return;
 busy=true;button.disabled=true;
 for(const id of ["submit","back","cancel"])el(id).disabled=true;
 el("error").textContent="";
 try{
  await request("/api/action",{action:"contact_prepare"});
  const shared=await new Promise(resolve=>tg.requestContact(resolve));
  if(!shared){el("error").textContent="Nomor belum dibagikan. Kamu bisa mencoba lagi atau mengetiknya sendiri.";return;}
  button.textContent="Menghubungkan nomormu…";
  for(let i=0;i<30;i++){
   const result=await request("/api/action",{action:"contact_status"});
   if(result.phone_ready){busy=false;await action({action:"phone_shared"});return;}
   await new Promise(resolve=>setTimeout(resolve,700));
  }
  el("error").textContent="Nomor belum diterima. Coba tombolnya lagi atau masukkan nomor secara manual.";
 }catch(e){el("error").textContent=e.message;}
 finally{
  busy=false;button.disabled=false;button.textContent="📱 Kirim Nomor Telepon";
  for(const id of ["submit","back","cancel"])el(id).disabled=false;
 }
}
function render(next){state=next;const step=state.step;el("fields").replaceChildren();el("error").textContent="";el("submit").hidden=false;el("cancel").hidden=false;el("back").hidden=["choose","done","cancelled","unavailable"].includes(step);el("submit").textContent="Lanjutkan →";
 const stages=["choose","api","phone","otp","password","summary","done"];const pct=Math.max(15,(stages.indexOf(step)+1)/7*100);el("progress").style.background="linear-gradient(90deg,#c995ff "+pct+"%,#34283f "+pct+"%)";
 const copy={choose:["✨ Siapkan botmu.","Pilih layanan, hubungkan akun, dan mulai dari sini."],api:["🔑 Hubungkan akses API","Masukkan API ID dan API Hash milikmu untuk melanjutkan."],phone:["🔐 Hubungkan akunmu","Gunakan akun Telegram yang sama dengan akun pembuka bot induk."],otp:["✉️ Cek Telegrammu","Masukkan kode login yang dikirim Telegram untuk melanjutkan."],password:["🔐 Satu langkah lagi","Masukkan password verifikasi dua langkah akunmu."],token:["🔗 Hubungkan botmu","Masukkan token dari @BotFather. Kami akan memeriksa identitas bot sebelum melanjutkan."],summary:["✨ Siap diaktifkan?","Periksa identitas layananmu sebelum melanjutkan."],done:["✨ Semuanya siap.","Ruangmu sudah aktif dan siap digunakan 🤍"],cancelled:["🍃 Proses dibatalkan","Belum ada layanan baru yang diaktifkan. Kamu bisa mulai lagi dari bot induk kapan saja."]};
 const [title,subtitle]=copy[step]||["Hubungkan ruangmu","Buka formulir dari bot induk."];el("title").textContent=title;el("subtitle").textContent=subtitle;
 if(step==="choose"){
   choice="";for(const k of state.kinds||[]){const b=node("button",null,"service");b.type="button";const text=node("div",labels[k]);text.append(node("span",descriptions[k]));b.append(text,node("strong","↗"));b.onclick=()=>{choice=k;document.querySelectorAll(".service").forEach(n=>n.classList.remove("selected"));b.classList.add("selected");el("submit").textContent=k==="userbot"&&state.existing?"Hubungkan Ulang →":"Lanjutkan →";};el("fields").append(b);}
   if(state.existing)el("fields").append(node("p","✦ Userbotmu sudah terdaftar. Hubungkan ulang untuk memperbarui koneksi; pengaturanmu tetap tersimpan.","hint"));
 }
 if(step==="api"){field("api_id","API ID");field("api_hash","API Hash","password");el("fields").append(link("Ambil API ID & Hash ↗","https://my.telegram.org/auth"));}
 if(step==="phone"){
  if(tg?.requestContact&&tg.isVersionAtLeast?.("6.9")){
   const share=node("button","📱 Kirim Nomor Telepon","service");share.type="button";
   share.onclick=()=>sharePhone(share);el("fields").append(share);
   el("fields").append(node("p","Bagikan nomor akun yang sedang membuka Mini App. Telegram akan meminta persetujuanmu.","hint"));
  }
  field("phone","Nomor Telegram","text","Atau masukkan nomor lengkap dengan kode negara, misalnya +44… atau +62….");
  el("fields").append(node("p","Dengan melanjutkan, kamu mengizinkan ZΞI menjalankan Userbot dari akunmu. Sesi disimpan terenkripsi di server pengelola. Jangan gunakan server yang tidak kamu percaya.","hint"));
 }
 if(step==="otp")field("code","Kode Telegram","password");
 if(step==="password")field("password","Password 2FA","password");
 if(step==="token")field("bot_token","Token bot","password");
 if(step==="summary"){
   const box=node("div",null,"detail");for(const [key,value] of [["Layanan",labels[state.kind]],["Nama",state.identity?.name||state.identity?.username],["Akun",state.identity?.username?"@"+state.identity.username:String(state.identity?.id||"")]]){const row=node("p");row.append(node("span",key),node("b",value));box.append(row);}el("fields").append(box);el("submit").textContent="✨ Buat Sekarang";
 }
 if(step==="done"||step==="cancelled"){
   el("submit").hidden=true;el("cancel").hidden=true;
   if(step==="done"){el("fields").append(node("p","✦","success"));el("fields").append(node("p",state.kind==="userbot"?"Ketik "+(state.result?.prefix||".")+"help dari akunmu untuk mulai.":"Buka botmu dan gunakan /setting untuk mulai mengatur.","hint"));}
   if(step==="done"){const again=node("button","✨ Buat Layanan Lagi","quiet");again.type="button";again.onclick=()=>action({action:"new"});el("fields").append(again);}
   const target=step==="done"&&state.kind!=="userbot"?state.result?.username:state.helper;
   if(target){const a=link(step==="done"&&state.kind!=="userbot"?"Buka Bot ↗":"Kembali ke Bot Induk ↗","https://t.me/"+target);a.id="return";el("fields").append(a);}
 }
}
async function request(path,data){const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json",...(token?{Authorization:"Bearer "+token}:{})},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw new Error(result.error||"Koneksi belum tersedia.");return result;}
async function action(data){if(busy)return;busy=true;el("submit").disabled=true;el("cancel").disabled=true;el("back").disabled=true;el("error").textContent="";const old=el("submit").textContent;el("submit").textContent="⚡ Menghubungkan…";try{render(await request("/api/action",data));}catch(e){el("error").textContent=e.message;el("submit").textContent=old;}finally{busy=false;el("submit").disabled=false;el("cancel").disabled=false;el("back").disabled=false;}}
el("form").onsubmit=e=>{e.preventDefault();const value=id=>el(id)?.value||"";let data={action:state.step};if(state.step==="choose"){if(!choice){el("error").textContent="Pilih layananmu terlebih dahulu.";return;}data.kind=choice;}if(state.step==="api"){data.api_id=Number(value("api_id"));data.api_hash=value("api_hash").trim();}if(state.step==="phone")data.phone=value("phone").replace(/\s/g,"");if(state.step==="otp")data.code=value("code").trim();if(state.step==="password")data.password=value("password");if(state.step==="token")data.token=value("bot_token").trim();if(state.step==="summary")data.action="create";action(data);for(const id of ["code","password"])if(el(id))el(id).value="";};
el("back").onclick=()=>action({action:"back"});
el("cancel").onclick=()=>action({action:"cancel"});
(async()=>{tg?.ready();tg?.expand();try{if(token){try{render(await request("/api/action",{action:"status"}));return;}catch{token="";sessionStorage.removeItem("zei-session");}}const result=await request("/api/auth",{initData:tg?.initData||""});token=result.token;sessionStorage.setItem("zei-session",token);render(result);}catch(e){render({step:"unavailable"});el("submit").hidden=true;el("cancel").hidden=true;el("error").textContent=e.message;}})();
