/* Shared with offline Node tests; no runtime dependencies. */
(function (scope) {
  'use strict';
  const synonyms = [
    ['搜索','search','查找','检索','搜寻'], ['群管','群组管理','群管理','moderation','管理'],
    ['下载','download','downloader'], ['翻译','translate','translation','translator','互译'],
    ['群组','群聊','group','groups'], ['频道','channel','channels'],
    ['订阅','subscription','subscribe','rss'], ['验证码','进群验证','入群验证','验证','captcha'],
    ['广告','防广告','反垃圾','spam','antispam'], ['抽奖','lottery'],
    ['签到','打卡','attendance','checkin'], ['游戏','game','games'],
    ['工具','tool','tools'], ['人工智能','ai'], ['口令','提取码','提取'],
  ];
  const normalize = value => String(value || '').normalize('NFKC').trim().toLowerCase();
  const aliases = synonyms.flatMap(group => group.map(word => [word, group])).sort((a,b) => b[0].length-a[0].length);
  const ignored = new Set(['telegram','tg','电报','机器人','bot','bots']);
  function queryGroups(query) {
    const text = normalize(query).replace(/^@/,'').slice(0,120), groups = [];
    for (const word of text.split(/[\s,，、;；]+/u).filter(Boolean)) {
      if (ignored.has(word)) continue;
      const direct = aliases.find(([alias]) => alias === word);
      if (direct) { groups.push(direct[1]); continue; }
      if (!/[\u3400-\u9fff]/u.test(word)) { groups.push([word]); continue; }
      let position = 0, unmatched = '';
      const flush = () => { const part = unmatched.replace(/机器人/g,''); if (part && !ignored.has(part)) groups.push([part]); unmatched=''; };
      while (position < word.length) {
        const match = aliases.find(([alias]) => /[\u3400-\u9fff]/u.test(alias) && word.startsWith(alias,position));
        if (match) { flush(); groups.push(match[1]); position+=match[0].length; }
        else { unmatched+=word[position++]; }
      }
      flush();
    }
    return groups.length ? groups : (text ? [[text]] : []);
  }
  function createIndex(bots) {
    return bots.map((bot,order) => ({...bot,order,fields:{username:normalize(bot.username).replace(/^@/,''),names:[normalize(bot.name),normalize(bot.remoteName)],tags:(bot.tags||[]).map(normalize),description:normalize(bot.description),category:normalize(bot.categoryName)}}));
  }
  function scoreWord(fields,term) {
    let score=0;
    if (fields.username===term) score=120;
    else if (fields.username.startsWith(term)) score=65;
    else if (fields.username.includes(term)) score=45;
    for (const name of fields.names) {
      if (name===term) score=Math.max(score,100);
      else if (name.startsWith(term)) score=Math.max(score,60);
      else if (name.includes(term)) score=Math.max(score,40);
    }
    if (fields.tags.some(tag=>tag===term)) score=Math.max(score,30);
    else if (fields.tags.some(tag=>tag.includes(term))) score=Math.max(score,22);
    if (fields.description.includes(term)) score=Math.max(score,12);
    if (fields.category.includes(term)) score=Math.max(score,6);
    return score;
  }
  function search(index,query='',category='') {
    const text=normalize(query).slice(0,120), plain=text.replace(/^@/,''), groups=queryGroups(text), results=[];
    for (const bot of index) {
      if (category && bot.category!==category) continue;
      let score=0,matched=true;
      for (const group of groups) {
        const value=Math.max(...group.map((term,i)=>scoreWord(bot.fields,term)*(i===0||term===plain?1:.8)));
        if (!value) { matched=false; break; } score+=value;
      }
      if (!matched) continue;
      if (plain && bot.fields.username===plain) score+=1000;
      if (plain && bot.fields.names.includes(plain)) score+=500;
      results.push({bot,score});
    }
    return results.sort((a,b)=>b.score-a.score||a.bot.order-b.bot.order).map(result=>result.bot);
  }
  const api={normalize,queryGroups,createIndex,search};
  if (typeof module!=='undefined' && module.exports) module.exports=api;
  scope.BotAtlasSearch=api;
  if (typeof document==='undefined') return;
  const source=document.getElementById('search-data'); if (!source) return;
  const index=createIndex(JSON.parse(source.textContent)), input=document.getElementById('bot-search'), form=document.getElementById('search-form'), clear=document.getElementById('clear-search'), results=document.getElementById('search-results'), empty=document.getElementById('empty-state');
  const sections=[...document.querySelectorAll('[data-category-section]')], filters=[...document.querySelectorAll('[data-filter]')], cards=new Map([...document.querySelectorAll('[data-bot-id]')].map(card=>[card.dataset.botId,card])), allowed=new Set(filters.map(filter=>filter.dataset.filter));
  let selected='',timer,composing=false;
  input.disabled=false; form.querySelector('[type=submit]').disabled=false;
  filters.forEach(filter=>{filter.setAttribute('role','button');filter.setAttribute('aria-pressed','false');});
  function render(writeURL) {
    const query=input.value.trim().slice(0,120),found=search(index,query,selected),searching=Boolean(query);
    document.body.dataset.searching=String(searching);
    sections.forEach(section=>{section.hidden=searching||Boolean(selected&&section.dataset.categorySection!==selected);});
    results.hidden=!searching||!found.length;
    const grid=document.getElementById('results-grid'); grid.replaceChildren();
    if (searching) {
      const fragment=document.createDocumentFragment();
      for (const bot of found) { const card=cards.get(bot.id).cloneNode(true);card.removeAttribute('data-bot-id');card.querySelectorAll('[data-search-url]').forEach(link=>{link.href=link.dataset.searchUrl;});fragment.append(card); }
      grid.append(fragment);
    }
    empty.hidden=found.length!==0; clear.hidden=!query;
    filters.forEach(filter=>filter.setAttribute('aria-pressed',String(filter.dataset.filter===selected)));
    document.getElementById('result-status').textContent=query?`找到 ${found.length} 个相关机器人 · 按相关性排序`:`共 ${found.length} 个机器人 · 按用途浏览`;
    document.getElementById('reset-filters').hidden=!query&&!selected;
    if (writeURL) { const url=new URL(location.href);query?url.searchParams.set('q',query):url.searchParams.delete('q');selected?url.searchParams.set('category',selected):url.searchParams.delete('category');history.replaceState(null,'',url.pathname+url.search+url.hash); }
  }
  function restore() { const params=new URL(location.href).searchParams;input.value=(params.get('q')||'').slice(0,120);const category=params.get('category')||'';selected=allowed.has(category)?category:'';render(false); }
  function reset() { clearTimeout(timer);input.value='';selected='';render(true);input.focus(); }
  form.addEventListener('submit',event=>{event.preventDefault();clearTimeout(timer);render(true);});
  input.addEventListener('compositionstart',()=>{composing=true;clearTimeout(timer);});
  input.addEventListener('compositionend',()=>{composing=false;clearTimeout(timer);timer=setTimeout(()=>render(true),100);});
  input.addEventListener('input',()=>{if(!composing){clearTimeout(timer);timer=setTimeout(()=>render(true),100);}});
  clear.addEventListener('click',()=>{clearTimeout(timer);input.value='';render(true);input.focus();});
  filters.forEach(filter=>{const choose=event=>{event.preventDefault();clearTimeout(timer);selected=filter.dataset.filter;render(true);};filter.addEventListener('click',choose);filter.addEventListener('keydown',event=>{if(event.key===' ')choose(event);});});
  document.getElementById('reset-filters').addEventListener('click',reset);document.getElementById('empty-reset').addEventListener('click',reset);addEventListener('popstate',restore);restore();
})(typeof globalThis!=='undefined'?globalThis:this);
