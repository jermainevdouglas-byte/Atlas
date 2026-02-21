function loadUnits(){
var prop=document.getElementById("propertySelect");
var unitSel=document.getElementById("unitSelect");
if(!prop||!unitSel)return;var propId=prop.value;
unitSel.innerHTML='<option value="">Select...</option>';if(!propId)return;
fetch("/api/units?property_id="+encodeURIComponent(propId)).then(function(r){return r.json();}).then(function(data){
if(!data.ok)return;
data.units.forEach(function(u){var opt=document.createElement("option");opt.value=u.unit_label;
opt.textContent=u.unit_label+(u.is_occupied?" (occupied)":"");opt.disabled=!!u.is_occupied;unitSel.appendChild(opt);});
}).catch(function(e){console.error(e);});}
document.addEventListener("DOMContentLoaded",function(){
var prop=document.getElementById("propertySelect");
if(prop)prop.addEventListener("change",loadUnits);loadUnits();});

