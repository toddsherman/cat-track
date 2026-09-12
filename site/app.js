/* Cat Track: small, dependency-free views of the paired collar recordings. */
(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const peach = "#B64832", toast = "#31566B", paper = "#F4F1EA", ink = "#1D1C19";
  const darkPeach = "#e38e77", darkToast = "#8ab1c6";
  let data, selectedHour = 7, selectedDay = "all", restDay = 0, restBin = 156;
  let activityGeometry, overlapGeometry, frame;
  const fixed = (n, digits = 1) => Number(n).toFixed(digits);
  const percentage = (n) => `${Math.round(n * 100)}%`;
  const dateLabel = (date) => new Date(`${date}T12:00:00`).toLocaleDateString("en-US", {month:"short", day:"numeric"});
  const hourLabel = (hour) => hour === 0 || hour === 24 ? "Midnight" : hour === 12 ? "Noon" : `${hour % 12} ${hour < 12 ? "a.m." : "p.m."}`;
  const clock = (minute) => {
    const h = Math.floor(minute / 60) % 24, m = Math.floor(minute % 60);
    return `${h % 12 || 12}${m ? `:${String(m).padStart(2, "0")}` : ""} ${h < 12 ? "a.m." : "p.m."}`;
  };
  const rangeLabel = (hour) => hour === 11 ? "11 a.m.–noon" : hour === 23 ? "11 p.m.–midnight" : `${hour % 12 || 12}–${(hour + 1) % 12 || 12} ${hour < 12 ? "a.m." : "p.m."}`;
  const pathFor = (rows, key, x, y) => rows.map((p, i) => `${i ? "L" : "M"}${x(p.hour + .5).toFixed(2)},${y(p[key]).toFixed(2)}`).join(" ");
  const currentRows = () => selectedDay === "all" ? data.hourly : data.days.find(d => d.date === selectedDay).hourly;

  function mealGuides(x, top, bottom, color, labelY) {
    const breakfast = x(435), dinnerStart = x(1110), dinnerEnd = x(1140);
    return `<g class="meal-guides" pointer-events="none">
      <rect class="dinner-window" data-start-minute="1110" data-end-minute="1140" x="${dinnerStart}" y="${top}" width="${dinnerEnd-dinnerStart}" height="${bottom-top}" fill="${color}" opacity=".09"/>
      <line class="breakfast-guide" data-minute="435" x1="${breakfast}" x2="${breakfast}" y1="${top}" y2="${bottom}" stroke="${color}" stroke-dasharray="4 5" opacity=".65"/>
      <line x1="${dinnerStart}" x2="${dinnerStart}" y1="${top}" y2="${bottom}" stroke="${color}" stroke-dasharray="2 4" opacity=".65"/>
      <line x1="${dinnerEnd}" x2="${dinnerEnd}" y1="${top}" y2="${bottom}" stroke="${color}" stroke-dasharray="2 4" opacity=".65"/>
      <text x="${breakfast}" y="${labelY}" fill="${color}" font-family="Arial,Helvetica,sans-serif" font-size="10" text-anchor="middle">Breakfast</text>
      <text x="${(dinnerStart+dinnerEnd)/2}" y="${labelY}" fill="${color}" font-family="Arial,Helvetica,sans-serif" font-size="10" text-anchor="middle">Dinner</text>
    </g>`;
  }

  function renderActivity() {
    const host = $("#activity-chart"), w = Math.max(280, host.clientWidth), h = w < 600 ? 255 : 340;
    const margin = {l:38, r:12, t:33, b:43};
    const plotW = w - margin.l - margin.r, plotH = h - margin.t - margin.b;
    const top = Math.max(200, Math.ceil(Math.max(...data.days.flatMap(d => d.hourly.flatMap(r => [r.peach, r.toast]))) / 50) * 50);
    const x = hour => margin.l + hour / 24 * plotW;
    const y = value => margin.t + plotH - value / top * plotH;
    activityGeometry = {w, h, x, y, margin, plotW, plotH};
    const rows = currentRows();
    let contents = `<rect x="${x(0)}" y="${margin.t}" width="${x(6)-x(0)}" height="${plotH}" fill="${paper}" opacity=".055"/><rect x="${x(22)}" y="${margin.t}" width="${x(24)-x(22)}" height="${plotH}" fill="${paper}" opacity=".055"/>`;
    for (let value = 0; value <= top; value += top > 300 ? 100 : 50) {
      contents += `<line class="chart-grid" x1="${x(0)}" x2="${x(24)}" y1="${y(value)}" y2="${y(value)}"/><text class="chart-text" fill="#c5beb0" text-anchor="end" x="${margin.l-10}" y="${y(value)+4}">${Math.round(value)}</text>`;
    }
    contents += `<text class="chart-text" x="${margin.l}" y="12" fill="#c5beb0">mg</text>`;
    for (const hour of [0,6,12,18,24]) {
      const label = w < 440 ? (hour === 0 || hour === 24 ? "12 a.m." : hour === 12 ? "12 p.m." : `${hour%12} ${hour<12?"a.m.":"p.m."}`) : hourLabel(hour);
      contents += `<text class="chart-text" text-anchor="${hour===0?"start":hour===24?"end":"middle"}" x="${x(hour)}" y="${h-11}" fill="#c5beb0">${label}</text>`;
    }
    contents += mealGuides(minute => x(minute/60), margin.t, y(0), "#c5beb0", 16);
    contents += `<path class="activity-line" d="${pathFor(rows, "peach", x, y)}" stroke="${darkPeach}"/><path class="activity-line" d="${pathFor(rows, "toast", x, y)}" stroke="${darkToast}"/>`;
    contents += `<line id="activity-cursor" y1="${margin.t}" y2="${y(0)}" stroke="${paper}" stroke-dasharray="3 5" opacity=".55"/><circle id="peach-cursor" r="5" fill="${darkPeach}" stroke="#25241f" stroke-width="2"/><circle id="toast-cursor" r="5" fill="${darkToast}" stroke="#25241f" stroke-width="2"/><rect class="pointer-area" x="${x(0)}" y="${margin.t}" width="${plotW}" height="${plotH}" fill="transparent"/>`;
    host.innerHTML = `<svg viewBox="0 0 ${w} ${h}" aria-hidden="true">${contents}</svg>`;
    const move = event => {
      const bounds = host.getBoundingClientRect();
      const hour = Math.min(23, Math.max(0, Math.floor(((event.clientX - bounds.left)*w/bounds.width - margin.l)/plotW*24)));
      if (selectedHour !== hour) {selectedHour = hour; updateActivityReadout();}
    };
    host.onpointermove = move;
    host.onclick = move;
    updateActivityReadout();
  }

  function updateActivityReadout() {
    if (!activityGeometry) return;
    const row = currentRows()[selectedHour], {x,y} = activityGeometry;
    $("#activity-cursor").setAttribute("x1", x(selectedHour+.5));
    $("#activity-cursor").setAttribute("x2", x(selectedHour+.5));
    for (const name of ["peach", "toast"]) {
      $(`#${name}-cursor`).setAttribute("cx", x(selectedHour+.5));
      $(`#${name}-cursor`).setAttribute("cy", y(row[name]));
    }
    $("#hour-slider").value = selectedHour;
    $("#hour-output").textContent = rangeLabel(selectedHour);
    $("#activity-readout").innerHTML = `<strong>${rangeLabel(selectedHour)}</strong><span class="peach-text">Peach <b>${fixed(row.peach)} mg</b></span><span class="toast-text">Toast <b>${fixed(row.toast)} mg</b></span>`;
    $("#activity-chart").setAttribute("aria-label", `Hourly collar movement. At ${rangeLabel(selectedHour)}, Peach ${fixed(row.peach)} mg and Toast ${fixed(row.toast)} mg. Meal guides show our usual breakfast around 7:15 a.m. and dinner around 6:30 to 7 p.m. Use the hour slider for other values.`);
  }

  function individualRestRuns(segments, bit) {
    const runs = [];
    for (const [start, end, state] of segments) {
      // Missing paired time stays unknown for both cats. Merge unchanged states
      // so a change in the other cat does not split this cat's continuous rest.
      const status = state === 4 ? "missing" : state & bit ? "rest" : "other";
      const previous = runs.at(-1);
      if (previous && previous[2] === status && Math.abs(previous[1]-start) < .00001) {
        previous[1] = end;
      } else {
        runs.push([start, end, status]);
      }
    }
    return runs;
  }

  function renderOverlap() {
    const host = $("#overlap-chart"), w = Math.max(280, host.clientWidth);
    const compact = w < 500;
    const margin = {l: compact ? 48 : 65, r: compact ? 40 : 56, t:42, b:38};
    const rowH = compact ? 54 : 62;
    const plotW = w-margin.l-margin.r, plotH = rowH*data.overlap.runs.length;
    const h = plotH+margin.t+margin.b;
    const x = minute => margin.l + minute/1440*plotW;
    overlapGeometry = {x, w, margin, rowH};
    let contents = `<defs><pattern id="rest-missing-pattern" patternUnits="userSpaceOnUse" width="6" height="6"><rect width="6" height="6" fill="#E9E4D9"/><path d="M-1 1L1-1M0 6L6 0M5 7L7 5" stroke="#8D887E" stroke-width="1.5"/></pattern></defs>`;

    // Human sleep spans midnight, so shade both ends of each calendar day.
    for (const [start, end] of [[0,360],[1320,1440]]) {
      contents += `<rect class="human-sleep-band" data-start-minute="${start}" data-end-minute="${end}" x="${x(start)}" y="${margin.t-7}" width="${x(end)-x(start)}" height="${plotH+14}" fill="#B58A43" opacity=".18"/>`;
    }
    for (const minute of [360,1320]) {
      contents += `<line x1="${x(minute)}" x2="${x(minute)}" y1="${margin.t-7}" y2="${margin.t+plotH+7}" stroke="#B58A43" stroke-dasharray="3 4"/>`;
    }
    contents += `<text x="${w-margin.r+8}" y="12" fill="#666157" font-family="Arial,Helvetica,sans-serif" font-size="${compact?9:11}">Both</text>`;
    data.overlap.runs.forEach((day, i) => {
      const cy = margin.t+i*rowH, barY = cy+9, laneH = (rowH-20)/2;
      const daily = data.daily.find(d => d.date===day.date);
      contents += `<text x="${margin.l-10}" y="${cy+rowH/2+4}" text-anchor="end" fill="${ink}" font-family="Arial,Helvetica,sans-serif" font-size="${compact?11:12}">${dateLabel(day.date)}</text>`;
      for (const [cat, bit, color, offset] of [["Toast",2,toast,0],["Peach",1,peach,laneH+2]]) {
        const laneY = barY+offset;
        contents += `<g class="rest-lane" data-cat="${cat}" data-date="${day.date}" data-lane-y="${laneY}"><rect class="rest-track" x="${x(0)}" y="${laneY}" width="${plotW}" height="${laneH}" fill="#E9E4D9"/>`;
        for (const [start,end,status] of individualRestRuns(day.segments,bit)) {
          if (status === "other") continue;
          const fill = status === "missing" ? "url(#rest-missing-pattern)" : color;
          contents += `<rect class="rest-interval" data-status="${status}" data-start-minute="${start}" data-end-minute="${end}" x="${x(start)}" y="${laneY}" width="${x(end)-x(start)}" height="${laneH}" fill="${fill}"/>`;
        }
        contents += `</g>`;
      }
      contents += `<text class="overlap-day-total" x="${w-margin.r+8}" y="${cy+rowH/2+4}" fill="${ink}" font-family="Arial,Helvetica,sans-serif" font-size="${compact?11:12}">${fixed(daily.bothRestHours24h)}h</text><rect data-overlap-row="${i}" x="${margin.l}" y="${cy}" width="${plotW}" height="${rowH}" fill="transparent"/>`;
    });
    contents += mealGuides(x, margin.t-7, margin.t+plotH+7, "#666157", 18);
    for (const hour of compact ? [0,6,12,18,24] : [0,6,12,18,22,24]) {
      const label = compact ? `${hour%12 || 12}${hour<12 || hour===24?'a':'p'}` : hourLabel(hour);
      contents += `<text class="overlap-axis-label" x="${x(hour*60)}" y="${h-8}" fill="#666157" font-family="Arial,Helvetica,sans-serif" font-size="${compact?10:12}" text-anchor="${hour===0?'start':hour===24?'end':'middle'}">${label}</text>`;
    }
    contents += `<rect id="overlap-selected-row" x="${margin.l-2}" width="${plotW+4}" height="${rowH-10}" fill="none" stroke="${ink}" stroke-width="1" opacity=".4" pointer-events="none"/><line id="overlap-cursor" y1="${margin.t}" y2="${h-margin.b}" stroke="${paper}" stroke-width="2" pointer-events="none"/><line id="overlap-cursor-outline" y1="${margin.t}" y2="${h-margin.b}" stroke="${ink}" stroke-width=".75" pointer-events="none"/>`;
    host.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Full 24-hour rest on six dates, midnight to midnight. Ochre bands mark human sleep time, 10 p.m. to 6 a.m. Each daily bar has Toast in blue on top and Peach in red below. Color means that cat is resting; pale sections mean no rest detected. Hatched sections are missing paired data. Meal guides show our usual breakfast around 7:15 a.m. and dinner around 6:30 to 7 p.m. Totals at right are shared rest per 24 hours. Use the controls below to inspect values.">${contents}</svg>`;
    const inspect = event => {
      const bounds = host.getBoundingClientRect();
      const px = (event.clientX-bounds.left)*w/bounds.width;
      const py = (event.clientY-bounds.top)*h/bounds.height;
      const row = Math.floor((py-margin.t)/rowH);
      if (row<0 || row>=data.days.length) return;
      restDay = row;
      restBin = Math.max(0,Math.min(287,Math.floor((px-margin.l)/plotW*288)));
      updateRestReadout();
    };
    host.onpointermove = event => {if (event.pointerType !== "touch") inspect(event);};
    host.onclick = inspect;
    updateRestReadout();
  }

  function updateRestReadout() {
    if (!overlapGeometry) return;
    const day = data.days[restDay], minute = restBin*5;
    const bin = day.timeline.find(row => row.minute === minute);
    $("#overlap-day").value = String(restDay);
    $("#overlap-time").value = restBin;
    $("#overlap-time-output").textContent = clock(minute);
    const humanSleep = minute < 360 || minute >= 1320;
    $("#overlap-time").setAttribute("aria-valuetext", `${clock(minute)} to ${clock(minute+5)}${humanSleep ? ", human sleep time" : ""}`);
    const {x,margin,rowH} = overlapGeometry;
    $("#overlap-selected-row").setAttribute("y", margin.t+restDay*rowH+5);
    for (const selector of ["#overlap-cursor","#overlap-cursor-outline"]) {
      $(selector).setAttribute("x1",x(minute+2.5)); $(selector).setAttribute("x2",x(minute+2.5));
    }
    if (!bin || bin.coverage === 0) {
      $("#overlap-readout").textContent = `${dateLabel(day.date)}, ${clock(minute)}: no paired recording for this interval.`;
      return;
    }
    $("#overlap-readout").innerHTML = `<strong>${dateLabel(day.date)} · ${clock(minute)}–${clock(minute+5)}</strong> &nbsp; <span class="toast-text">Toast resting ${percentage(bin.toastRest)}</span> · <span class="peach-text">Peach ${percentage(bin.peachRest)}</span> · <strong>Both ${percentage(bin.bothRest)}</strong>${humanSleep?' <span class="human-sleep-tag">Human sleep time</span>':""}${bin.coverage<1?" · Partial recording":""}`;
  }

  function renderDaily() {
    const host=$("#daily-chart"), w=Math.max(280,host.clientWidth), h=w<500?265:310;
    const margin={l:33,r:6,t:34,b:40}, max=90, plotH=h-margin.t-margin.b;
    const y=value=>margin.t+plotH-value/max*plotH;
    const cell=(w-margin.l-margin.r)/data.daily.length, bw=Math.min(36,cell*.24);
    let contents="";
    for (const value of [0,30,60,90]) contents+=`<line x1="${margin.l}" x2="${w-margin.r}" y1="${y(value)}" y2="${y(value)}" stroke="#D4CEC2"/><text x="${margin.l-8}" y="${y(value)+4}" fill="#666157" text-anchor="end" font-family="Arial" font-size="11">${value}</text>`;
    contents+=`<text x="${margin.l}" y="14" fill="#666157" font-family="Arial" font-size="11">mg</text>`;
    data.daily.forEach((day,i)=>{
      const center=margin.l+cell*(i+.5), highlight=day.date==="2026-09-04";
      if(highlight)contents+=`<rect x="${center-cell*.45}" y="${margin.t-13}" width="${cell*.9}" height="${plotH+22}" fill="#B58A43" opacity=".11"/>`;
      for(const [name,offset,color] of [["peach",-bw-2,peach],["toast",2,toast]]){
        contents+=`<rect x="${center+offset}" y="${y(day[name])}" width="${bw}" height="${y(0)-y(day[name])}" fill="${color}"><title>${dateLabel(day.date)}: ${name==='peach'?'Peach':'Toast'} ${fixed(day[name])} mg</title></rect><text x="${center+offset+bw/2}" y="${y(day[name])-9}" fill="${color}" text-anchor="middle" font-family="Arial" font-size="${w<500?10:12}">${Math.round(day[name])}</text>`;
      }
      const parts=dateLabel(day.date).split(" ");
      contents+=`<text x="${center}" y="${h-17}" fill="${ink}" text-anchor="middle" font-family="Arial" font-size="${w<500?10:12}">${parts[0]} ${parts[1]}</text>`;
    });
    host.innerHTML=`<svg viewBox="0 0 ${w} ${h}" aria-hidden="true">${contents}</svg>`;
  }

  function updateSensitivity(){
    const cutoff=Number($("#threshold-select").value);
    const rows=data.sensitivity.filter(row=>row.threshold_mg===cutoff && row.min_bout_minutes===5);
    $("#sensitivity-result").innerHTML=rows.map(row=>`<span>${row.cat}<strong>${fixed(row.rest_hours_per_day,2)} h</strong></span>`).join("");
  }

  function updateHeroTrace(){
    const x=hour=>hour/24*400, y=value=>70-value/160*58;
    $(".trace-peach").setAttribute("d",pathFor(data.hourly,"peach",x,y));
    $(".trace-toast").setAttribute("d",pathFor(data.hourly,"toast",x,y));
  }

  function bind(){
    data.days.forEach((day,i)=>{
      const activityOption=new Option(dateLabel(day.date),day.date);
      $("#day-select").add(activityOption);
      $("#overlap-day").add(new Option(dateLabel(day.date),String(i)));
    });
    $("#day-select").addEventListener("change",event=>{
      selectedDay=event.target.value;
      $("#activity-period").textContent=selectedDay==="all"?"Average of August 31–September 5, 2026":`${dateLabel(selectedDay)}, 2026 · individual day`;
      renderActivity();
    });
    $("#hour-slider").addEventListener("input",event=>{selectedHour=Number(event.target.value);updateActivityReadout();});
    $("#overlap-day").addEventListener("change",event=>{restDay=Number(event.target.value);updateRestReadout();});
    $("#overlap-time").addEventListener("input",event=>{restBin=Number(event.target.value);updateRestReadout();});
    $("#threshold-select").addEventListener("change",updateSensitivity);
    let resizeTimer;
    window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{renderActivity();renderOverlap();renderDaily();},120);});
    renderActivity();renderOverlap();renderDaily();updateHeroTrace();updateSensitivity();
    document.documentElement.dataset.charts="ready";
  }

  document.querySelectorAll('a[href^="#"]').forEach(anchor=>anchor.addEventListener("click",event=>{
    const target=$(anchor.getAttribute("href"));
    if(!target)return;
    event.preventDefault();
    if(target.tagName==="DETAILS")target.open=true;
    if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
    target.focus({preventScroll:true});
    target.scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"});
    history.replaceState(null,"",anchor.getAttribute("href"));
  }));
  function progress(){
    const denominator=document.documentElement.scrollHeight-innerHeight;
    $(".reading-progress span").style.transform=`scaleX(${denominator>0?scrollY/denominator:0})`;
    frame=null;
  }
  window.addEventListener("scroll",()=>{if(!frame)frame=requestAnimationFrame(progress);},{passive:true});
  progress();
  fetch("data.json").then(response=>{if(!response.ok)throw new Error("Unable to load chart data");return response.json();})
    .then(payload=>{data=payload;bind();})
    .catch(()=>{
      for(const selector of ["#activity-chart","#overlap-chart","#daily-chart"]){
        $(selector).innerHTML='<p class="chart-loading">The chart data could not load. <a href="data.json">Open the data</a> or reload the page.</p>';
      }
      for(const selector of ["#day-select","#hour-slider","#overlap-day","#overlap-time","#threshold-select"])$(selector).disabled=true;
      $("#activity-readout").textContent="The headline findings remain available above.";
      $("#overlap-readout").textContent="Interactive rest data is unavailable.";
      document.documentElement.dataset.charts="error";
    });
})();
