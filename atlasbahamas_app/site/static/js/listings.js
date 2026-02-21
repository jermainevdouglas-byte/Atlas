function escapeHtml(s){return String(s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#039;"}[c];})}
var COMPARE_KEY="atlasbahamas_compare_ids";
function currentFilters(){
  return {
    maxPrice:document.getElementById("maxPrice").value||"",
    location:document.getElementById("location").value||"",
    beds:document.getElementById("beds").value||"",
    category:document.getElementById("category").value||""
  };
}
function buildParams(f){
  var p=new URLSearchParams();
  if(f.maxPrice)p.set("maxPrice",f.maxPrice);
  if(f.location)p.set("location",f.location);
  if(f.beds)p.set("beds",f.beds);
  if(f.category)p.set("category",f.category);
  return p;
}
function getCompare(){try{return JSON.parse(localStorage.getItem(COMPARE_KEY)||"[]").filter(function(x){return Number(x)>0;});}catch(e){return [];}}
function setCompare(ids){localStorage.setItem(COMPARE_KEY,JSON.stringify(ids.slice(0,3)));}
function toggleCompare(id){
  var ids=getCompare();
  var n=Number(id);
  var i=ids.indexOf(n);
  if(i>=0)ids.splice(i,1);
  else{
    if(ids.length>=3){alert("You can compare up to 3 listings.");return;}
    ids.push(n);
  }
  setCompare(ids);
  renderCompareTray();
}
function renderCompareTray(){
  var tray=document.getElementById("compareTray");
  if(!tray)return;
  var ids=getCompare();
  if(!ids.length){tray.style.display="none";tray.innerHTML="";return;}
  tray.style.display="block";
  tray.innerHTML="<b>Compare:</b> "+ids.length+" selected"
    +' <a class="ghost-btn" href="/compare?ids='+encodeURIComponent(ids.join(","))+'" style="margin-left:8px;">Open Compare</a>'
    +' <button class="ghost-btn" type="button" id="clearCompare" style="margin-left:8px;">Clear</button>';
  var clear=document.getElementById("clearCompare");
  if(clear)clear.onclick=function(){setCompare([]);renderCompareTray();};
}
function syncSaveSearchForm(){
  var f=currentFilters();
  var m=document.getElementById("saveSearchMaxPrice");
  var l=document.getElementById("saveSearchLocation");
  var b=document.getElementById("saveSearchBeds");
  var c=document.getElementById("saveSearchCategory");
  if(m)m.value=f.maxPrice;
  if(l)l.value=f.location;
  if(b)b.value=f.beds;
  if(c)c.value=f.category;
}
function fetchListings(){
var p=buildParams(currentFilters());
fetch("/api/listings?"+p.toString()).then(function(r){return r.json();}).then(function(data){
if(!data.ok)return;
var wrap=document.getElementById("listingResults");wrap.innerHTML="";
var compare=getCompare();
data.listings.forEach(function(l){
var row=document.createElement("div");row.className="prop-item";
var checked=compare.indexOf(Number(l.id))>=0?"checked":"";
row.innerHTML='<img src="'+escapeHtml(l.image_url)+'" alt="" style="width:68px;height:52px;border-radius:14px;border:1px solid rgba(255,255,255,.14);object-fit:cover;background:rgba(0,0,0,.2);">'
+'<div><div style="font-weight:1000;">'+escapeHtml(l.title)+' &bull; $'+Number(l.price).toLocaleString()+'</div>'
+'<div class="muted" style="font-size:12px;margin-top:4px;">'+escapeHtml(l.location)+' &bull; '+l.beds+' bed / '+l.baths+' bath &bull; '+escapeHtml(l.category)+'</div></div>'
+'<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">'
+'<label class="badge" style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" data-compare-id="'+l.id+'" '+checked+'>Compare</label>'
+'<button class="badge" type="button" data-share-url="'+escapeHtml(location.origin+"/listing/"+l.id)+'" data-share-title="'+escapeHtml(l.title)+'">Share</button>'
+'<a class="badge" href="/listing/'+l.id+'" style="text-decoration:none;">View</a>'
+'</div>';
wrap.appendChild(row);});
document.getElementById("resultCount").textContent=data.listings.length+" result(s)";
Array.prototype.forEach.call(document.querySelectorAll("input[data-compare-id]"),function(cb){
  cb.addEventListener("change",function(e){toggleCompare(e.target.getAttribute("data-compare-id"));});
});
syncSaveSearchForm();
renderCompareTray();
}).catch(function(e){console.error(e);});}
document.addEventListener("DOMContentLoaded",function(){
var btn=document.getElementById("applyFilters");
if(btn)btn.addEventListener("click",function(e){e.preventDefault();fetchListings();});
var compareBtn=document.getElementById("openCompare");
if(compareBtn)compareBtn.addEventListener("click",function(){
  var ids=getCompare();
  if(!ids.length){alert("Select listing(s) to compare first.");return;}
  location.href="/compare?ids="+encodeURIComponent(ids.join(","));
});
["maxPrice","location","beds","category"].forEach(function(id){
  var el=document.getElementById(id); if(el)el.addEventListener("change",syncSaveSearchForm);
});
syncSaveSearchForm();
fetchListings();});

