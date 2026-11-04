export const STUDIO_SCENES=[
 {id:'director',title:'临场小导演',scene:'ball',prompt:'“演一只周一上班的鸭。”中途改口：“别走，只用头，最后摇头。”',ready:true,
 controls:[['排练：周一上班','duck_direct',{title:'周一上班',steps:[{action:'stand'},{action:'walk',duration:1.5},{action:'look_down'},{action:'shake_head'}]}],['改成只用头','duck_direct',{title:'只用头部',head_only:true,steps:[{action:'tilt_head'},{action:'look_down'},{action:'shake_head'}]}]]},
 {id:'delivery',title:'嘴硬快递员 2.0',scene:'carry',ready:true,controls:[['开始递送','duck_delivery',{operation:'start'}],['停，别松嘴','duck_delivery',{operation:'pause'}],['继续送','duck_delivery',{operation:'resume'}]],prompt:'“把小棒送过去。”中途：“停，别松嘴。”然后：“继续送。”'},
 {id:'conductor',title:'评委当指挥',scene:'seated',ready:true,controls:[['C 先唱，再 A','duck_conduct',{operation:'start',order:['c','a']}],['下一位换 B','duck_conduct',{operation:'queue',order:['b']}]],prompt:'“C 先唱，再轮到 A。”临时改口：“下一位换 B。”'},
 {id:'voice',title:'鸭子的声音身份',scene:'ball',ready:true,prompt:'轻沙哑、带鼻音，偶尔嘎一声。'},
 {id:'recipe',title:'我教你一个暗号',scene:'ball',ready:true,controls:[
 ['教：下班＝摇头＋坐下','duck_recipe',{operation:'draft',name:'下班',plan:{title:'下班仪式',steps:[{action:'shake_head'},{action:'sit'}]}}],
 ['确认保存','duck_recipe',{operation:'confirm',name:'下班'}],
 ['改：删掉摇头','duck_recipe',{operation:'draft',name:'下班',plan:{title:'安静下班',steps:[{action:'sit'}]}}],
 ['执行“下班”','duck_recipe',{operation:'run',name:'下班'}],
 ['删除暗号','duck_recipe',{operation:'delete',name:'下班'}]],prompt:'“以后‘下班’就是摇头、坐下。”再说：“删掉摇头。”'},
 {id:'coach',title:'世界杯小教练',scene:'ball',ready:true,controls:[
 ['只观察，不动','duck_coach',{operation:'observe'}],
 ['明确摆到左脚前','duck_coach',{operation:'prepare',foot:'left'}],
 ['明确摆到右脚前','duck_coach',{operation:'prepare',foot:'right'}],
 ['左脚踢准备好的球','duck_coach',{operation:'kick',foot:'left'}],
 ['右脚踢准备好的球','duck_coach',{operation:'kick',foot:'right'}]],prompt:'“先看看能不能踢，别动。”确认后：“改用右脚。”'},
 {id:'game',title:'鸭王说',scene:'ball',ready:true,controls:[
 ['设口令：鸭王说','duck_game',{operation:'configure',prefix:'鸭王说'}],
 ['试：点头（漏口令）','duck_game',{operation:'play',plan:{title:'点头',steps:[{action:'nod'}]}},'点头'],
 ['试：鸭王说点头','duck_game',{operation:'play',plan:{title:'点头',steps:[{action:'nod'}]}},'鸭王说点头'],
 ['换口令：船长说','duck_game',{operation:'configure',prefix:'船长说'}],
 ['试：船长说点头','duck_game',{operation:'play',plan:{title:'点头',steps:[{action:'nod'}]}},'船长说点头']],prompt:'“只有带‘鸭王说’才执行。”试着漏掉口令，再换个口令。'},
 {id:'rubber',title:'会追问的橡皮鸭',scene:'ball',ready:true,controls:[
 ['排练：接口报错','duck_discuss',{fact:'接口调用报错',question:'请求返回的状态码是多少？'}],
 ['修正：请求没发出','duck_discuss',{fact:'请求没有发出去',replace_facts:true,question:'点击按钮后，控制台出现什么错误？'}]],prompt:'“接口打不开，先别给答案，帮我理清楚。”'},
 {id:'focus',title:'专注搭子',scene:'ball',ready:true,controls:[
 ['坐稳后计时十秒','duck_focus',{operation:'start',seconds:10}],
 ['再延十秒','duck_focus',{operation:'extend',seconds:10}],
 ['取消提醒','duck_focus',{operation:'cancel'}]],prompt:'“十秒后站起来叫我。”随后：“再延十秒。”'},
 {id:'persona',title:'换班不换鸭',scene:'ball',ready:true,prompt:'严教练与摸鱼搭子，同一个问题，两种反应。'},
];
