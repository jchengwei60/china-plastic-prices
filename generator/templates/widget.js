/* 塑价365 今日塑料价格挂件 https://pla365.com/tools/widget/ */
(function(){var D={"date":"2026-11-10","items":[{"s":"pp","n":"PP拉丝","p":"11100","c":"0.00%"},{"s":"lldpe","n":"LLDPE","p":"9975","c":"0.00%"},{"s":"hdpe","n":"HDPE","p":"10900","c":"-2.02%"},{"s":"ldpe","n":"LDPE","p":"12067","c":"-1.23%"},{"s":"pvc","n":"PVC SG-5","p":"4875","c":"-1.12%"},{"s":"abs","n":"ABS","p":"12083","c":"0.00%"},{"s":"ps","n":"PS","p":"12333","c":"-1.86%"},{"s":"pet","n":"PET","p":"8379","c":"0.00%"}]};
(function(){
var el=document.getElementById('pla365-widget');if(!el||el.getAttribute('data-done'))return;el.setAttribute('data-done','1');
var want=(el.getAttribute('data-items')||'').split(',').filter(Boolean);
var items=D.items.filter(function(i){return !want.length||want.indexOf(i.s)>=0});
var dark=el.getAttribute('data-theme')==='dark';
var bg=dark?'#1f2329':'#fff',fg=dark?'#f2f3f5':'#1f2329',sub=dark?'#9aa0a8':'#7a808a',ln=dark?'#333840':'#eceef1';
var h='<div style="font:14px/1.5 -apple-system,BlinkMacSystemFont,PingFang SC,Microsoft YaHei,sans-serif;max-width:420px;border:1px solid '+ln+';border-top:3px solid #e3241b;border-radius:8px;background:'+bg+';color:'+fg+';padding:10px 12px;box-sizing:border-box">'
+'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px"><b style="font-size:15px">今日塑料价格</b><span style="color:'+sub+';font-size:12px">'+D.date+' · 元/吨</span></div>'
+'<table style="width:100%;border-collapse:collapse">';
items.forEach(function(i){var c=parseFloat(i.c),col=c>0?'#d4281f':(c<0?'#1e8c46':sub);
h+='<tr style="border-top:1px solid '+ln+'"><td style="padding:5px 0"><a href="https://pla365.com/'+i.s+'/" target="_blank" rel="noopener" style="color:'+fg+';text-decoration:none">'+i.n+'</a></td><td style="text-align:right;font-weight:600">'+i.p+'</td><td style="text-align:right;width:64px;color:'+col+'">'+(c>0?'+':'')+i.c+'</td></tr>';});
h+='</table><div style="margin-top:6px;font-size:12px;color:'+sub+'">生意社品种基准价，非牌号成交价</div></div>';
var box=document.createElement('div');box.innerHTML=h;
var a=el.querySelector('a');el.insertBefore(box,el.firstChild);
if(a){a.style.cssText='display:inline-block;margin-top:4px;font-size:12px;color:'+sub;}
})();
})();