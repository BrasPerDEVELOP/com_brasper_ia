/* Inline SVG icon set — self-contained (works offline via file://). window.icon(name,color,size) */
(function(){
  var P={
    gauge:'<path d="M12 14a2 2 0 0 0 2-2c0-1-2-5-2-5s-2 4-2 5a2 2 0 0 0 2 2z"/><path d="M5 18a8 8 0 1 1 14 0"/>',
    flow:'<rect x="3" y="3" width="6" height="6" rx="1.5"/><rect x="15" y="15" width="6" height="6" rx="1.5"/><path d="M6 9v3a3 3 0 0 0 3 3h6"/>',
    template:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>',
    chat:'<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    inbox:'<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13l3.5 7v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
    chart:'<path d="M3 3v18h18"/><rect x="7" y="11" width="3" height="6" rx="1"/><rect x="12" y="7" width="3" height="10" rx="1"/><rect x="17" y="13" width="3" height="4" rx="1"/>',
    book:'<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    cast:'<path d="M2 16a6 6 0 0 1 6 6M2 12a10 10 0 0 1 10 10"/><circle cx="3" cy="21" r="1.2"/><path d="M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/>',
    puzzle:'<path d="M19.4 13c.6 0 1.1-.5 1.1-1.1V8.5A1.5 1.5 0 0 0 19 7h-2.5V5.6a2.1 2.1 0 1 0-4.2 0V7H9a1.5 1.5 0 0 0-1.5 1.5V10h-1.4a2.1 2.1 0 1 0 0 4.2H7.5V17A1.5 1.5 0 0 0 9 18.5h2.5v-1.4a2.1 2.1 0 1 1 4.2 0v1.4H19a1.5 1.5 0 0 0 1.5-1.5v-2.5"/>',
    ai:'<path d="M12 3v3M12 18v3M5 7l2 2M17 15l2 2M3 12h3M18 12h3M7 17l-2 2M19 7l-2 2"/><circle cx="12" cy="12" r="4"/>',
    creditcard:'<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20M6 15h4"/>',
    users:'<circle cx="9" cy="8" r="3.2"/><path d="M3 20a6 6 0 0 1 12 0"/><path d="M16 5.5a3.2 3.2 0 0 1 0 6M21 20a6 6 0 0 0-4-5.7"/>',
    gear:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    shield:'<path d="M12 2 4 5v6c0 5 3.5 9 8 11 4.5-2 8-6 8-11V5z"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    mic:'<path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3M8 22h8"/>',
    user:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    check:'<path d="M20 6 9 17l-5-5"/>',
    x:'<path d="M18 6 6 18M6 6l12 12"/>',
    headset:'<path d="M3 14v-2a9 9 0 0 1 18 0v2"/><path d="M21 16a2 2 0 0 1-2 2h-1v-6h1a2 2 0 0 1 2 2zM3 16a2 2 0 0 0 2 2h1v-6H5a2 2 0 0 0-2 2z"/><path d="M19 18a4 4 0 0 1-4 3h-3"/>',
    arrow:'<path d="M5 12h14M13 6l6 6-6 6"/>',
    arrowleft:'<path d="M19 12H5M11 6l-6 6 6 6"/>',
    play:'<path d="M6 4l14 8-14 8z"/>',
    pause:'<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
    eye:'<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7"/><circle cx="12" cy="12" r="3"/>',
    refresh:'<path d="M3 11a9 9 0 0 1 15-5.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 13a9 9 0 0 1-15 5.7L3 16"/><path d="M3 21v-5h5"/>',
    form:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    branch:'<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="9" r="2.5"/><path d="M6 8.5v7M8.5 6H13a2 2 0 0 1 2 2v.5"/>',
    plug:'<path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',
    chev:'<path d="m6 9 6 6 6-6"/>',
    chevr:'<path d="m9 6 6 6-6 6"/>',
    chevl:'<path d="m15 6-6 6 6 6"/>',
    rocket:'<path d="M4.5 16.5 3 21l4.5-1.5M14 6l4 4M6.5 12.5a8 8 0 0 1 5-5C16 6 18 4 21 3c-1 3-3 5-4.5 9.5a8 8 0 0 1-5 5z"/><circle cx="14.5" cy="9.5" r="1.3"/>',
    building:'<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 6h2M13 6h2M9 10h2M13 10h2M9 14h2M13 14h2M10 22v-3h4v3"/>',
    globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18z"/>',
    calendar:'<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/>',
    file:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    upload:'<path d="M12 16V4M7 9l5-5 5 5"/><path d="M5 20h14"/>',
    trash:'<path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/>',
    edit:'<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    dots:'<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/>',
    external:'<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    send:'<path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/>',
    lock:'<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    key:'<circle cx="8" cy="15" r="4"/><path d="M11 12 20 3M17 6l2 2M14 9l2 2"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h0"/>',
    alert:'<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h0"/>',
    copy:'<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    dollar:'<path d="M12 2v20M17 6.5C17 4.5 14.8 3.5 12 3.5S7 4.7 7 7s2.2 3 5 3.5 5 1.3 5 3.5-2.2 3.5-5 3.5-5-1-5-3"/>',
    sparkles:'<path d="M12 3l1.6 4.2L18 9l-4.4 1.8L12 15l-1.6-4.2L6 9l4.4-1.8z"/><path d="M19 14l.7 1.8L21 16.5l-1.3.7L19 19l-.7-1.8L17 16.5l1.3-.7z"/>',
    layers:'<path d="M12 3 2 8l10 5 10-5z"/><path d="M2 13l10 5 10-5M2 18l10 5 10-5"/>',
    whatsapp:'__WA__',
    facebook:'__FB__',
    instagram:'<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1.1" fill="currentColor" stroke="none"/>',
    telegram:'<path d="M21 4 3 11l5 2 2 6 3-4 5 4z"/>'
  };
  window.icon=function(name,color,size){
    color=color||'currentColor'; size=size||18;
    var body=P[name]||'';
    if(name==='whatsapp'){
      return '<svg width="'+size+'" height="'+size+'" viewBox="0 0 24 24" fill="none"><path d="M12 2a10 10 0 0 0-8.5 15.3L2 22l4.8-1.5A10 10 0 1 0 12 2z" fill="'+color+'"/><path d="M8.5 7.4c-.2 0-.5.1-.7.4-.3.3-1 1-1 2.4s1 2.7 1.1 2.9c.2.2 2 3.1 4.9 4.3 2.4 1 2.9.8 3.4.7.5 0 1.6-.6 1.8-1.3.2-.6.2-1.2.2-1.3-.1-.1-.3-.2-.6-.3l-1.7-.8c-.2-.1-.4-.1-.6.1l-.6.8c-.2.2-.3.2-.6.1-.7-.3-1.5-.6-2.4-1.5-.4-.4-.7-.9-1-1.3-.1-.2 0-.4.1-.5l.4-.5c.1-.1.1-.3.2-.5 0-.1 0-.3-.1-.4l-.7-1.7c-.2-.4-.4-.4-.6-.4z" fill="#fff"/></svg>';
    }
    if(name==='facebook'){
      return '<svg width="'+size+'" height="'+size+'" viewBox="0 0 24 24" fill="'+color+'"><path d="M22 12a10 10 0 1 0-11.6 9.9v-7H7.9V12h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.5h-1.3c-1.2 0-1.6.8-1.6 1.6V12h2.8l-.4 2.9h-2.4v7A10 10 0 0 0 22 12z"/></svg>';
    }
    var stroke=(name==='instagram')?'1.8':'1.7';
    return '<svg width="'+size+'" height="'+size+'" viewBox="0 0 24 24" fill="none" stroke="'+color+'" stroke-width="'+stroke+'" stroke-linecap="round" stroke-linejoin="round">'+body+'</svg>';
  };
})();
