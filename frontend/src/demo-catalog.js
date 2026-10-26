// Authored theatre scripts. Rehearsal dialogue is never labelled as a cloud answer.
const line=(id,text,role='鸭子')=>({kind:'line',id,text,role});
const command=(id,text,actions)=>({kind:'command',id,text,role:'预录指令',actions});
export const DEMOS=[
 {id:'identity',title:'你是哪只鸭？',hook:'先自我介绍，再用身体签个到。',scene:'ball',source:'方案 1 · 幕一',duration:'约 25 秒',
  steps:[line('identity-intro','欢迎来到鸭王入职第一天。先让今天的主角签个到。','旁白'),command('identity-command','请读取当前状态，告诉我你在什么场景，然后点头打个招呼。',['nod']),{kind:'inspect',label:'读取本轮真实状态'},line('identity-end','我的身体在物理仿真里。成绩看现场，不拿历史记录冒充今天。')]},
 {id:'interview',title:'反向招聘人类',hook:'今天，轮到鸭子面试评委。',scene:'ball',source:'故事方案 · 1',duration:'约 30 秒',
  steps:[line('interview-intro','面试开始。让本鸭向大家问好，但不许说点头两个字。'),command('interview-command','请向在场的评委打个招呼，表示一下认可。',['nod']),line('interview-joke','恭喜录用，工资是每天两句夸奖。'),command('interview-shake','明天就要交付了，请抖抖毛，表演一下紧张。',['bear_shake']),line('interview-end','能不能不加班？这道题超出了面试范围。')]},
 {id:'interrupt',title:'闭嘴，换我说',hook:'话说一半，旧声音和动作一起停。',scene:'ball',source:'方案 0 · 2',duration:'约 30 秒',
  steps:[line('interrupt-intro','这只鸭话很多，但你永远拥有最后的控制权。','旁白'),{kind:'interrupt',id:'interrupt-old',text:'请先表演闪身步，再用一段长话介绍你自己。',actions:['flash_step'],replacement:'interrupt-new',replacementText:'停止旧任务。现在只点头一次。'},line('interrupt-end','旧回复已经停下。现在，轮到新需求说了算。')]},
 {id:'change',title:'甲方又改需求了',hook:'旧任务撤销，没做的动作不能偷偷接着做。',scene:'ball',source:'故事方案 · 2',duration:'约 30 秒',
  steps:[line('change-intro','原需求：跳舞，抖毛，最后点头。客户的消息刚刚来了。','旁白'),{kind:'interrupt',id:'change-old',text:'请依次表演闪身步，狗熊哆嗦毛，最后点头。',actions:['flash_step','bear_shake','nod'],replacement:'change-new',replacementText:'取消刚才整套任务。只向左转一下，不要抖毛，也不要点头。',next:'turn_left'},line('change-end','舞蹈已撤回。刚才取消的工作，记得算工时。')]},
 {id:'football',title:'鸭界世界杯记者会',hook:'左右脚轮番上场，成绩只认真实触球。',scene:'ball',source:'故事方案 · 3',duration:'约 35 秒',
  steps:[line('football-intro','欢迎来到鸭界世界杯。球可以踢偏，成绩不能瞎编。','旁白'),command('football-left','请用左脚踢球。',['kick_left']),{kind:'inspect',label:'左脚实测成绩'},command('football-right','现在请用右脚踢球。',['kick_right']),{kind:'inspect',label:'右脚实测成绩'},line('football-end','战术是教练的，脚法是本鸭的。实际位移，请看裁判的数据。')]},
 {id:'delivery',title:'嘴硬快递员',hook:'项目最后一根救命稻草，终于落地了。',scene:'carry',source:'故事方案 · 4 / 方案 0 · 3',duration:'约 40 秒',
  steps:[line('delivery-intro','这根小棒，是项目最后一根救命稻草。接下来，这活我用嘴干。'),command('delivery-command','请用嘴夹起小棒，搬过去，再放下。每一步成功后再继续。',['pick_up','carry','put_down']),{kind:'inspect',label:'本轮交付验收'},line('delivery-end','确认放稳，才算交付。需求终于落地了。')]},
 {id:'duel',title:'一屏双魂，舞林争霸',hook:'两个独立房间，同一时刻，两套舞步。',scene:'ball',source:'方案 0 · 4',duration:'约 30 秒',
  steps:[line('duel-intro','左边闪身步，右边抖抖毛。两个房间，各跳各的，不串台。','旁白'),{kind:'duel',id:'duel-left',text:'请表演闪身步。',second:'duel-right',secondText:'请表演狗熊哆嗦毛。'},line('duel-end','两份动作记录，两套物理世界。谁也没有抢走谁的身体。')]},
 {id:'lonely',title:'孤独鸭的寻友记',hook:'先背过身，再转回来：看见需要满足条件。',scene:'duo',source:'方案 0 · 5',duration:'约 40 秒',
  steps:[line('lonely-intro','同伴就在附近，但背对着对方，可不算看见。','旁白'),{kind:'action',name:'turn_left',target:'both',duration:3},{kind:'action',name:'find_companion',expectFailure:true},line('lonely-turn','没有发现，就调整方向。不能把希望当作检测结果。'),{kind:'action',name:'turn_right',target:'both',duration:3},command('lonely-find','请发现同伴。',['find_companion']),{kind:'inspect',label:'视野与距离验证'},line('lonely-end','原来同伴一直在附近。这一次，我们是真的看见了。')]},
 {id:'debut',title:'社恐鸭组团出道',hook:'先见面，再合唱，组合名叫“鸭力山大”。',scene:'duo',source:'故事方案 · 5',duration:'约 35 秒',
  steps:[line('debut-intro','一个鸭是打工，两个鸭就是创业团队。请两位成员见面。','旁白'),command('debut-meet','请发现同伴，然后相向碰面。',['find_companion','collide']),{kind:'inspect',label:'本轮接触验收'},command('debut-chorus','你们的团名叫鸭力山大。请来一段同步合唱。',['chorus']),line('debut-end','我们的第一张专辑，叫明天一定交付。')]},
 {id:'chorale',title:'四声部谢幕',hook:'从两条旋律，到四层和声。听见成员的加入。',scene:'duo',source:'方案 1 · 幕三',duration:'约 35 秒',
  steps:[line('chorale-intro','这次不是两只鸭唱同一个音。低音和高音先开场，中音和次中音依次加入。','旁白'),{kind:'music'},line('chorale-end','有人加入，其他成员不换声部。有人离开，留住他的席位。这就是合唱团的默契。')]},
 {id:'tabletop',title:'桌上不掉拍',hook:'四只鸭一张桌。掉下去，也要把歌唱完。',scene:'table',source:'新增桌上四鸭合唱',duration:'约 45 秒',
  steps:[line('table-intro','四位歌手，一张桌子。请把掌声留到最后，桌子的面积有限。','旁白'),{kind:'table_music'},line('table-end','我没掉队，只是把低音部，搬到了楼下。')]},
 {id:'seated',title:'轮到我开唱',hook:'一起坐着唱，轮到谁，谁站起来。',scene:'seated',source:'新增坐姿合唱',duration:'约 45 秒',
  steps:[{kind:'seated_music'}]},
 {id:'stage',title:'黄仁勋的四只小鸭',hook:'散落、哈欠、排队。选几只翻跟头，再四鸭同拍齐舞。',scene:'stage',source:'GTC 互动桥段 · 中文改编',duration:'约 60–100 秒',
  steps:[command('stage-gather','嘿，小家伙们，到中间来站成一排，让大家看你们表演。',['stage_gather']),command('stage-roll','选中的小鸭们，能一起翻个跟头吗？',['stage_roll']),command('stage-dance','一起表演闪身步和狗熊抖抖毛吧。',['stage_dance'])]}

];
export const AUDIO_VERSION='personas-stage-selection-v2';
export const ACTION_NAMES={stage_gather:'四鸭集结排队',stage_roll:'点名前滚翻并归位',stage_dance:'四鸭同拍齐舞',stage_poke:'物理轻戳',scene_stage:'准备四鸭发布会',sit:'坐下',stand:'站起来',scene_seated:'准备坐姿合唱舞台',seated_show:'坐姿合唱与独唱交接',scene_table:'准备桌面舞台',table_show:'桌上合唱',scene_ball:'准备球场',scene_carry:'准备搬运场景',scene_duo:'准备双鸭场景',nod:'点头',walk:'前进',turn_left:'左转',turn_right:'右转',flash_step:'闪身步',bear_shake:'抖毛',kick_left:'左脚踢球',kick_right:'右脚踢球',pick_up:'夹起',carry:'搬运',put_down:'放下',find_companion:'发现同伴',collide:'相向碰面',chorus:'双声部合唱',stop:'停止'};
export const AUDIO_LINES=DEMOS.flatMap(d=>d.steps.flatMap(s=>[
 ...(s.id?[{id:s.id,text:s.text,role:s.role??'预录指令'}]:[]),
 ...(s.replacement?[{id:s.replacement,text:s.replacementText,role:'预录指令'}]:[]),
 ...(s.second?[{id:s.second,text:s.secondText,role:'预录指令'}]:[]),
]));
