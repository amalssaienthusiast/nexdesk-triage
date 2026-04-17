/*
  NexDesk Mission Control — Deep Integration App
*/

const state = {
  sessions: [],
  heatmap: {},
  ticketDetailsCache: {}
};

// ── DOM Elements ──
const els = {
  clock: document.getElementById('clock'),
  statusDot: document.getElementById('status-dot'),
  statusLabel: document.getElementById('status-label'),
  pipeline: document.getElementById('pipeline-container'),
  flagFeed: document.getElementById('flag-feed'),
  heatmap: document.getElementById('heatmap-container'),
  
  // Stats
  statActive: document.getElementById('stat-active'),
  statSla: document.getElementById('stat-sla'),
  statBreaches: document.getElementById('stat-breaches'),
  statEsc: document.getElementById('stat-escalations'),
  statKb: document.getElementById('stat-kb'),
  statSavings: document.getElementById('stat-savings'),
  
  // Analytics
  kbPct: document.getElementById('kb-util-pct'),
  kbBar: document.getElementById('kb-bar'),
  escPct: document.getElementById('esc-util-pct'),
  escBar: document.getElementById('esc-bar'),
  
  // Alert Banner
  alertBanner: document.getElementById('alert-banner'),
  alertIcon: document.getElementById('alert-icon'),
  alertTitle: document.getElementById('alert-title'),
  alertDesc: document.getElementById('alert-desc'),
  alertTicket: document.getElementById('alert-ticket'),
  alertContent: document.getElementById('alert-content'),
  
  // Modal
  modal: document.getElementById('ticket-modal'),
  modalClose: document.getElementById('modal-close'),
  modalId: document.getElementById('modal-ticket-id'),
  modalStage: document.getElementById('modal-stage'),
  modalRole: document.getElementById('modal-role'),
  modalSubject: document.getElementById('modal-subject'),
  modalDesc: document.getElementById('modal-desc'),
  modalActions: document.getElementById('modal-actions'),
  modalKb: document.getElementById('modal-kb'),
  modalSub: document.getElementById('modal-submitter'),
  modalDept: document.getElementById('modal-dept'),
  modalReward: document.getElementById('modal-reward'),
  modalGtPri: document.getElementById('modal-gt-pri'),
  modalEsc: document.getElementById('modal-escalations'),
  modalFlags: document.getElementById('modal-flags'),
};

// ── Helpers ──
function formatTime() {
  const d = new Date();
  els.clock.textContent = d.toISOString().substr(11, 8) + ' UTC';
}
setInterval(formatTime, 1000);
formatTime();

function setStatus(isOk) {
  if (isOk) {
    els.statusDot.className = 'status-dot w-3 h-3 rounded-full bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.5)]';
    els.statusLabel.textContent = 'SYSTEM ONLINE';
  } else {
    els.statusDot.className = 'status-dot w-3 h-3 rounded-full bg-red-500 animate-pulse shadow-[0_0_10px_rgba(239,68,68,0.5)]';
    els.statusLabel.textContent = 'DISCONNECTED';
  }
}

// ── Alert Banner Logic ──
let activeAlertTimer = null;
function triggerAlert(flag) {
  if (activeAlertTimer) return; // Don't override currently showing alert
  
  let bgClass = "bg-blue-900/90 border-blue-500";
  let icon = "ℹ️";
  if (flag.severity === "critical") {
    bgClass = "bg-red-900/90 border-red-500";
    icon = "🚨";
  } else if (flag.severity === "warn") {
    bgClass = "bg-orange-900/90 border-orange-500";
    icon = "⚠️";
  }
  
  els.alertContent.className = `p-4 rounded-xl shadow-lg border-l-4 flex items-center justify-between ${bgClass} backdrop-blur-md`;
  els.alertIcon.textContent = icon;
  els.alertTitle.textContent = flag.type.replace(/_/g, ' ');
  els.alertDesc.textContent = flag.message;
  els.alertTicket.textContent = flag.ticket_id || 'SYSTEM';
  
  els.alertBanner.classList.add('animate-slide-down');
  
  activeAlertTimer = setTimeout(() => {
    els.alertBanner.classList.remove('animate-slide-down');
    activeAlertTimer = null;
  }, 5000);
}

// ── Rendering ──

function renderPipeline() {
  const stages = ["Received", "Classification", "Routing", "Escalation Check", "Resolution", "Closed"];
  
  // Group sessions by stage
  const byStage = {};
  stages.forEach(s => byStage[s] = []);
  
  state.sessions.forEach(s => {
    if (byStage[s.stage]) {
      byStage[s.stage].push(s);
    }
  });

  els.pipeline.innerHTML = `<div class="grid grid-cols-1 md:grid-cols-6 gap-2 h-full">
    ${stages.map((stage, idx) => `
      <div class="flex flex-col">
        <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2 text-center">${stage} <span class="bg-slate-700 text-slate-300 px-1.5 py-0.5 rounded-full ml-1">${byStage[stage].length}</span></div>
        <div class="flex-1 pipeline-stage-box overflow-y-auto max-h-[400px]">
          ${byStage[stage].map(s => {
            const isEscalated = s.current_role.startsWith("L2");
            return `
            <div class="pipeline-ticket ${s.priority}" onclick="openTicketModal('${s.session_id}')">
              <div class="truncate pr-2">
                <div class="text-[10px] font-mono text-slate-400">${s.ticket_id}</div>
                <div class="text-xs font-semibold text-slate-200 truncate w-24">${s.subject}</div>
              </div>
              <div class="text-right">
                ${isEscalated ? `<span class="text-[9px] bg-purple-900/50 text-purple-300 px-1 rounded block mb-1">L2</span>` : ''}
                <span class="text-[10px] ${s.elapsed_minutes > s.sla_deadline_minutes ? 'text-red-400 font-bold' : 'text-slate-500'}">${Math.floor(s.elapsed_minutes)}m</span>
              </div>
            </div>`;
          }).join('')}
        </div>
      </div>
    `).join('')}
  </div>`;
}

function renderHeatmap() {
  const priorities = ["critical", "high", "medium", "low"];
  const categories = ["network", "hardware", "software", "access", "security", "other"];
  
  let html = '';
  // Left axis labels
  html += `<div class="col-span-5 grid grid-cols-6 gap-1 mb-1">`;
  categories.forEach(c => html += `<div class="text-[9px] text-slate-500 text-center uppercase truncate">${c.substring(0,4)}</div>`);
  html += `</div>`;
  
  html += `<div class="col-span-5 grid grid-cols-6 gap-1">`;
  
  // Find max for scaling
  let maxCount = 1;
  const matrix = state.heatmap || {};
  priorities.forEach(p => {
    categories.forEach(c => {
      const v = (matrix[p] && matrix[p][c]) ? matrix[p][c] : 0;
      if (v > maxCount) maxCount = v;
    });
  });

  priorities.forEach(p => {
    categories.forEach(c => {
      const count = (matrix[p] && matrix[p][c]) ? matrix[p][c] : 0;
      const intensity = count > 0 ? 0.2 + (0.8 * (count / maxCount)) : 0;
      
      let baseHue = 200; // Blue for low
      if (p === 'critical') baseHue = 0; // Red
      else if (p === 'high') baseHue = 30; // Orange
      else if (p === 'medium') baseHue = 45; // Yellow
      
      const bgColor = count > 0 ? `hsl(${baseHue}, 80%, ${intensity * 50}%)` : 'rgba(30, 41, 59, 0.5)';
      const textColor = count > 0 ? '#fff' : 'transparent';
      
      html += `
        <div class="heatmap-cell" style="background: ${bgColor}; color: ${textColor}">
          ${count}
          <div class="heatmap-tooltip">${p} | ${c} (${count})</div>
        </div>
      `;
    });
  });
  html += `</div>`;
  els.heatmap.innerHTML = html;
}

function renderFeed(events, alerts) {
  let html = '';
  
  // Render critical alerts first
  alerts.slice(0, 5).forEach(f => {
    let color = 'text-blue-400';
    if(f.severity==='critical') color = 'text-red-400';
    if(f.severity==='warn') color = 'text-orange-400';
    
    html += `
      <div class="border-l-2 border-slate-700 pl-2 py-1 bg-slate-800/30">
        <div class="flex justify-between items-start">
          <span class="${color} font-bold">${f.type}</span>
          <span class="text-[9px] text-slate-500">${f.ticket_id}</span>
        </div>
        <div class="text-slate-300 mt-1">${f.message}</div>
      </div>
    `;
    
    // Trigger banner for criticals
    if(f.severity === 'critical') triggerAlert(f);
  });
  
  // Then normal events
  events.slice(0, 10).forEach(e => {
    let typeStyle = 'text-slate-400';
    if (e.type === 'step') typeStyle = 'text-green-400';
    else if (e.type === 'reset') typeStyle = 'text-cyan-400';
    
    html += `
      <div class="flex gap-3 text-sm border-l-2 border-transparent pl-2">
        <span class="text-slate-500">${e.timestamp.substr(0,8)}</span>
        <span class="${typeStyle}">[${e.type.toUpperCase()}]</span>
        <span class="text-slate-300 truncate">${e.message}</span>
      </div>
    `;
  });
  
  if (!html) html = '<div class="text-slate-600 italic">No anomalies detected.</div>';
  els.flagFeed.innerHTML = html;
}

// ── Modals ──

async function openTicketModal(sessionId) {
  els.modal.classList.remove('hidden');
  els.modalSubject.textContent = "Loading...";
  els.modalActions.textContent = "";
  els.modalKb.innerHTML = "";
  els.modalEsc.innerHTML = "";
  els.modalFlags.innerHTML = "";
  
  try {
    const res = await fetch(`/api/dashboard/ticket/${sessionId}`);
    const data = await res.json();
    
    els.modalId.textContent = data.ticket_id;
    els.modalStage.textContent = data.done ? 'CLOSED' : 'ACTIVE';
    els.modalRole.textContent = data.current_role;
    els.modalSubject.textContent = data.subject;
    els.modalDesc.textContent = data.description;
    
    els.modalSub.textContent = data.submitter;
    els.modalDept.textContent = data.department;
    els.modalReward.textContent = data.total_reward.toFixed(4);
    
    const pri = data.ground_truth.priority;
    let priColor = 'text-blue-400';
    if(pri==='critical') priColor='text-red-400';
    if(pri==='high') priColor='text-orange-400';
    els.modalGtPri.innerHTML = `<span class="${priColor} font-bold uppercase">${pri}</span>`;
    
    els.modalActions.textContent = JSON.stringify(data.accumulated_actions, null, 2);
    
    if (data.kb_searches > 0) {
      els.modalKb.innerHTML = `<div class="bg-cyan-900/30 text-cyan-300 p-2 font-mono text-xs rounded border border-cyan-800">Agent performed ${data.kb_searches} successful KB queries during resolution.</div>`;
    } else {
      els.modalKb.innerHTML = `<div class="text-slate-600 italic text-xs">No KB searches performed.</div>`;
    }
    
    if (data.escalation_history && data.escalation_history.length > 0) {
      let eh = '';
      data.escalation_history.forEach((esc, i) => {
        eh += `<div class="ml-4 pl-2 border-l-2 border-purple-500/50 pb-2">
          <div class="text-purple-400 font-bold text-xs">→ ${esc.team}</div>
          <div class="text-slate-400 text-[10px]">Policy: ${esc.policy||'auto'} | Reason: ${esc.reason||'None provided'}</div>
        </div>`;
      });
      els.modalEsc.innerHTML = eh;
    } else {
      els.modalEsc.innerHTML = `<div class="text-slate-600 italic text-xs">Stayed at L1.</div>`;
    }
    
    if (data.active_flags && data.active_flags.length > 0) {
      let flagsHtml = '';
      data.active_flags.forEach(f => {
        let color = f.severity === 'critical' ? 'red' : (f.severity === 'warn' ? 'orange' : 'blue');
        flagsHtml += `<div class="bg-${color}-900/30 border border-${color}-800 p-2 rounded text-xs">
          <span class="text-${color}-400 font-bold">${f.type}</span>
          <p class="text-slate-300 mt-1">${f.message}</p>
        </div>`;
      });
      els.modalFlags.innerHTML = flagsHtml;
    } else {
      els.modalFlags.innerHTML = `<div class="text-slate-600 italic text-xs">No active flags.</div>`;
    }
    
  } catch (e) {
    els.modalSubject.textContent = "Error loading ticket details";
    console.error(e);
  }
}

els.modalClose.addEventListener('click', () => {
  els.modal.classList.add('hidden');
});

// ── Polling ──

async function fetchData() {
  try {
    const [dashRes, heatRes] = await Promise.all([
      fetch('/api/dashboard'),
      fetch('/api/dashboard/heatmap')
    ]);
    
    if (!dashRes.ok) throw new Error("API error");
    setStatus(true);
    
    const data = await dashRes.json();
    state.sessions = data.sessions;
    state.heatmap = await heatRes.json();
    
    // Update Stats
    els.statActive.textContent = data.total_active;
    els.statSla.textContent = Math.floor(state.sessions.reduce((acc, s) => acc + s.sla_deadline_minutes, 0) / (state.sessions.length || 1)) + "m";
    els.statBreaches.textContent = state.sessions.reduce((acc, s) => acc + s.sla_breaches, 0);
    els.statEsc.textContent = data.escalation_flows.length;
    els.statKb.textContent = data.kb_usage.searches;
    
    // Simulated Cost Savings Math ($25 per L2 manual escalate saved)
    const resolvedL1 = state.sessions.filter(s => s.done && s.current_role === "L1_Dispatcher").length;
    els.statSavings.textContent = "$" + (resolvedL1 * 25);
    
    // Update Analytics Bars
    const totalDone = data.total_active + data.total_complete;
    const kbPct = totalDone > 0 ? Math.floor((data.kb_usage.searches / totalDone) * 100) : 0;
    els.kbPct.textContent = `${Math.min(100, kbPct)}%`;
    els.kbBar.style.width = `${Math.min(100, kbPct)}%`;
    
    const escPct = totalDone > 0 ? Math.floor((data.escalation_flows.length / totalDone) * 100) : 0;
    els.escPct.textContent = `${Math.min(100, escPct)}%`;
    els.escBar.style.width = `${Math.min(100, escPct)}%`;
    
    renderPipeline();
    renderHeatmap();
    renderFeed(data.recent_events, data.alerts);
    
  } catch(e) {
    console.error(e);
    setStatus(false);
  }
}

// Initial fetch & poll
fetchData();
setInterval(fetchData, 2000);
