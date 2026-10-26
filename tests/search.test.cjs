const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createIndex,search}=require('../site/assets/search.js');
const root=path.join(__dirname,'..');
const bots=JSON.parse(fs.readFileSync(path.join(root,'data/bots.json'),'utf8')).bots;
const categories=JSON.parse(fs.readFileSync(path.join(root,'data/categories.json'),'utf8'));
const cat=new Map(categories.map(c=>[c.id,c]));
const liveIndex=createIndex(bots.filter(b=>b.url&&!(b.fetch.status==='dead'&&b.fetch.dead_streak>=3)).map(b=>({id:b.id,name:b.name||b.fetch.title||b.username,remoteName:b.fetch.title,username:b.username,description:b.notes,tags:b.tags,category:b.category,categoryName:cat.get(b.category).title})));
// Fixed examples test behavior independently of editorial additions/deletions.
const index=createIndex([
  {id:'jiso',name:'搜索示例',username:'@jiso',description:'搜索群组和频道',tags:['搜索'],category:'search',categoryName:'搜索'},
  {id:'dk_searcha_bot',name:'DK 搜索机器人',username:'@dk_searcha_bot',description:'关键词搜索群组、频道；口令提取',tags:['搜索','群组','口令'],category:'search',categoryName:'搜索'},
  {id:'dropmailbot',name:'邮箱示例',username:'@DropmailBot',description:'临时邮箱',tags:['邮箱'],category:'tools',categoryName:'工具'},
  {id:'translatebot',name:'翻译示例',username:'@TranslateBot',description:'翻译消息',tags:['翻译'],category:'translate',categoryName:'翻译'},
  {id:'freedlvideo_bot',name:'下载示例',username:'@freedlvideo_bot',description:'视频下载',tags:['下载'],category:'download',categoryName:'下载'},
]);
const ids=(q,c)=>search(index,q,c).map(b=>b.id);
test('username ignores @, case and full-width input',()=>{for(const q of ['@JISO','jiso','  @JiSo  ','＠ＪＩＳＯ']) assert.equal(ids(q)[0],'jiso');});
test('names and descriptions are searchable',()=>{assert.ok(ids('DK 搜索机器人').includes('dk_searcha_bot'));assert.ok(ids('临时邮箱').includes('dropmailbot'));});
test('Chinese compound and English synonyms work',()=>{assert.ok(ids('群组搜索').includes('dk_searcha_bot'));assert.ok(ids('search groups').includes('dk_searcha_bot'));assert.ok(ids('translation').includes('translatebot'));assert.ok(ids('download').includes('freedlvideo_bot'));});
test('tags include token extraction without claiming generic resource search',()=>{assert.ok(ids('提取码').includes('dk_searcha_bot'));assert.equal(ids('从未存在的内容XYZ').length,0);});
test('category intersects keyword results',()=>{assert.equal(ids('jiso','download').length,0);assert.ok(search(index,'','translate').every(b=>b.category==='translate'));});
test('empty query is stable and includes featured bots',()=>{assert.equal(ids('').length,index.length);assert.equal(new Set(ids('')).size,index.length);assert.ok(ids('','search').includes('jiso'));});
test('exact username wins over descriptive mentions, including an owned bot',()=>{const sample=createIndex([{id:'owned',name:'Station tool',username:'@owned_bot',description:'demo_bot',tags:[],category:'search',categoryName:'搜索'},{id:'exact',name:'Demo',username:'@demo_bot',description:'',tags:[],category:'tools',categoryName:'工具'}]);assert.equal(search(sample,'demo_bot')[0].id,'exact');});
test('literal markup and regex-like queries are harmless',()=>{assert.doesNotThrow(()=>search(index,'[.*</script>'));assert.equal(ids('[.*</script>').length,0);});
test('actual catalog remains searchable after editorial removals',()=>{const all=search(liveIndex,'');assert.equal(all.length,liveIndex.length);assert.equal(new Set(all.map(b=>b.id)).size,all.length);for(const bot of liveIndex)assert.equal(search(liveIndex,bot.username)[0].id,bot.id);});
test('one thousand searches keep a small catalog responsive',()=>{const start=performance.now();for(let i=0;i<1000;i++)search(liveIndex,i%2?'translation':'群组搜索');console.log(`1000 searches: ${(performance.now()-start).toFixed(0)} ms, ${liveIndex.length} bots`);});
