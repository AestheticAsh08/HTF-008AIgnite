/* Shared helpers: Leaflet + OpenStreetMap (open source), OSRM routing, Nominatim search */
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
var DEFAULT_CENTER=[10.1960,76.3860];

function mkMap(id,center,zoom){
  var m=L.map(id).setView(center||DEFAULT_CENTER,zoom||12);
  var tiles=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(m);
  tiles.on('tileerror',function(){
    if(window._tileWarned) return; window._tileWarned=true;
    var n=document.createElement('div'); n.className='flash error';
    n.textContent='Map tiles could not load. Check your internet connection (markers and distances still work).';
    var main=document.querySelector('main'); if(main) main.insertBefore(n,main.firstChild);
  });
  return m;
}
function pin(emoji){
  return L.divIcon({html:'<div class="emoji-pin">'+emoji+'</div>',className:'',iconSize:[28,28],iconAnchor:[14,26],popupAnchor:[0,-24]});
}
function hav(a,b,c,d){
  var r=6371,p=Math.PI/180,x=(c-a)*p,y=(d-b)*p;
  var h=Math.sin(x/2)*Math.sin(x/2)+Math.cos(a*p)*Math.cos(c*p)*Math.sin(y/2)*Math.sin(y/2);
  return 2*r*Math.asin(Math.sqrt(h));
}
/* Draw a road route (OSRM public server). Falls back to a straight dashed line. */
function drawRoute(group,from,to,color,cb){
  var url='https://router.project-osrm.org/route/v1/driving/'+from[1]+','+from[0]+';'+to[1]+','+to[0]+'?overview=full&geometries=geojson';
  fetch(url).then(function(r){return r.json();}).then(function(j){
    if(!j.routes||!j.routes.length) throw new Error('no route');
    var rt=j.routes[0];
    L.geoJSON(rt.geometry,{style:{color:color,weight:5,opacity:.8}}).addTo(group);
    cb&&cb({km:rt.distance/1000,min:rt.duration/60,road:true});
  }).catch(function(){
    L.polyline([from,to],{color:color,weight:4,dashArray:'6 8'}).addTo(group);
    var km=hav(from[0],from[1],to[0],to[1]);
    cb&&cb({km:km,min:km/25*60,road:false});
  });
}
function fmtLeft(m){
  if(m<=0) return 'expired';
  if(m<60) return m+' min';
  return Math.floor(m/60)+'h '+(m%60)+'m';
}
function fmtTime(ts){
  if(!ts) return '';
  var d=new Date(ts.replace(' ','T'));
  return d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
}
var STEPS=[['posted','Posted'],['accepted','Accepted'],['picked_up','Picked up'],['delivered','Delivered']];
function stepsHtml(status){
  var idx=STEPS.map(function(s){return s[0];}).indexOf(status);
  if(idx<0) return '';
  return '<div class="steps">'+STEPS.map(function(s,i){return '<span class="'+(i<=idx?'on':'')+'">'+s[1]+'</span>';}).join('')+'</div>';
}

/* Location picker: click map, drag marker, search a place, or use GPS. */
function initPicker(o){
  var map=mkMap(o.mapId,o.center,13), marker=null;
  var latEl=document.getElementById(o.latId), lngEl=document.getElementById(o.lngId);
  var addrEl=o.addrId?document.getElementById(o.addrId):null;
  function setPoint(lat,lng,reverse){
    if(marker){marker.setLatLng([lat,lng]);}
    else{
      marker=L.marker([lat,lng],{draggable:true}).addTo(map);
      marker.on('dragend',function(e){var p=e.target.getLatLng();setPoint(p.lat,p.lng,true);});
    }
    latEl.value=lat.toFixed(6); lngEl.value=lng.toFixed(6);
    if(o.onChange) setTimeout(function(){o.onChange(lat,lng);},0);
    if(reverse&&addrEl){
      fetch('https://nominatim.openstreetmap.org/reverse?format=json&lat='+lat+'&lon='+lng)
        .then(function(r){return r.json();}).then(function(j){if(j.display_name) addrEl.value=j.display_name;}).catch(function(){});
    }
  }
  map.on('click',function(e){setPoint(e.latlng.lat,e.latlng.lng,true);});
  var sb=document.getElementById(o.searchBtn), si=document.getElementById(o.searchInput);
  function search(){
    var q=si.value.trim(); if(!q) return;
    /* bias results toward the area currently shown, so a locality name picks the nearby one */
    var b=map.getBounds();
    var vb='&viewbox='+b.getWest()+','+b.getNorth()+','+b.getEast()+','+b.getSouth();
    fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1'+vb+'&q='+encodeURIComponent(q))
      .then(function(r){return r.json();}).then(function(j){
        if(!j.length){alert('Place not found. Try a different name or click on the map.');return;}
        var lat=parseFloat(j[0].lat),lng=parseFloat(j[0].lon);
        map.setView([lat,lng],16); setPoint(lat,lng,false);
        if(addrEl) addrEl.value=j[0].display_name;
      }).catch(function(){alert('Search failed (no internet?). Click on the map instead.');});
  }
  sb.addEventListener('click',search);
  si.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();search();}});
  var gb=document.getElementById(o.gpsBtn);
  if(gb) gb.addEventListener('click',function(){
    if(!navigator.geolocation){alert('Location not supported in this browser.');return;}
    navigator.geolocation.getCurrentPosition(function(p){
      map.setView([p.coords.latitude,p.coords.longitude],16);
      setPoint(p.coords.latitude,p.coords.longitude,true);
    },function(){alert('Could not get your location. Search or click on the map.');});
  });
  if(o.initial) {map.setView(o.initial,15); setPoint(o.initial[0],o.initial[1],false);}
  return map;
}

/* Indian food mark: green square+dot = veg, brown square+triangle = non-veg */
function dietMark(diet){
  var nv=diet==='nonveg';
  return '<span class="dmark '+(nv?'nonveg':'veg')+'" title="'+(nv?'Non-veg':'Veg')+'"></span>'+(nv?'Non-veg':'Veg');
}
