"""注入世界观+细纲后让 NovelEngine 写第1章。

策略：
- 跳过 plan_chapter（细纲已手写，不需 LLM 规划）
- 手动构造 ChapterPlan，含 7 个 scene_beats（来自 empty_rooms_ch01_outline.md）
- 把世界观手册核心条款塞入 novel_ledger_items，让 director/writer 读得到
- 直接调 write_chapter
"""

import os
import sys
import time
from pathlib import Path

os.environ["NOVEL_LLM_PROVIDER"] = "mimo"
os.environ["MIMO_API_KEY"] = "tp-crnpv8v46s2gchl6tdg0826m978ru63eo42uygeyssk7m3d2"

sys.path.insert(0, r"F:\12\语英")

from awp_rp_runtime_v2.storage.sqlite.database import Database
from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.runtime.novel_engine import NovelEngine
from awp_rp_runtime_v2.contracts.novel_project import NovelProject
from awp_rp_runtime_v2.contracts.novel_character import (
    NovelCharacter, CharacterRelationship,
)
from awp_rp_runtime_v2.contracts.novel_chapter import (
    ChapterPlan, BeatDetail, ContentSummary, PlotArrangement,
    CharacterAppearance, EndingDesign,
)
from awp_rp_runtime_v2.contracts.novel_ledger import LedgerItem


# === 世界观核心条款（精简版，留给 director/writer 在 prompt 里看到）===
WORLD_RULES = """【世界观核心】
世界三层：阳岸（生者） / 阴岸（死者执念雾区） / 夹缝走廊（事故撑裂的褶皱层）。
引魂人不是天选英雄，是1994年事故漏网者——都是受害者，失忆+失眠是脑被夹缝渗漏浸泡的副作用。
九种引魂香：引魂/安魂/识脸/缝魂/忘魂/寻路/锁门/召旧/反魂，各有代价；反魂香是禁术。
禁忌：一根香只对一魂；超时夹缝不闭；同引魂人身上缝魂香驻留不超3种；死亡不可逆。

【核心历史】
1994年12月17日江城老城区七处旧址同夜塌陷，234死78失踪。真相：1960年代"阿棉花计划"在七处地下做秘密濒死医疗实验，三十年后实验体意识同时觉醒引发夹缝同步开放。
林知夏1994年5岁，是78失踪中唯一年幼幸存者，被救后送孤儿院，记忆被抹除。
袁护士：1960年代阿棉花计划护士，1994年复活，被困夹缝三十年，是林知夏母亲的同父异母姐姐。

【七处旧址】1号=林知夏租的廉租房（义庄/民国诊所复合层） 2-6号第三卷末延伸钩 7号军管区=终章伏笔。

【异能分级】Lv.0失眠过目不忘→Lv.1起香人→Lv.2辨相师→Lv.3缝魂者→Lv.4引魂正执→Lv.5锁门人→Lv.6召旧者→Lv.7反魂者。林知夏开篇Lv.0。

【写作铁律】林知夏一律"她"；404小孩一律"其"；袁护士"她"；不写穿越系统重生；不写国家力量介入；不跨Lv.7；感情线让位主线；不写反派洗白；不用"夙愿/宿命/天选"等词。
"""


# === Chapter 1 七个 beat（来自细纲）===
BEATS_DATA = [
    {
        "beat_id": "b1",
        "description": "林知夏扛纸箱进403，跟袁护士交接钥匙。对话：袁护士递钥匙说「房东留的安神香，十二根」，林知夏问「这什么」，袁护士说「老方子，睡前点一根」就走了。林知夏内心吐槽：送租客香是什么操作。声控灯熄，防盗门合。下午3点对面筒子楼挡光。",
        "function_tag": "scene+character+prop", "density": "中", "budget_chars": 600,
    },
    {
        "beat_id": "b2",
        "description": "拆箱。对话/回忆：林知夏想起袁护士刚才说的「老方子，睡前点一根」，自言自语「老方子是什么方子」。抖出黑色外套，檀香味，和安神香同一个调子。对话/自言自语：「这不是我的衣服，谁塞进来的？」口袋掉出黄铜圆盘，背面044，抽屉焦痕严丝合缝。内心戏推断：前人留下的，这屋子换过多少租客。",
        "function_tag": "不安钩+物证", "density": "疏", "budget_chars": 400,
    },
    {
        "beat_id": "b3",
        "description": "午夜点香。对话/自言自语为主：林知夏边点边嘟囔「二十年前的香，包装纸都泛黄了，这能点着？」香灰七厘米弯曲悬空。她伸手碰——不是粉末。对话：「什么玩意儿，塑料的？」一捏碎三块。识破：蜡壳裹红色棉线。对话：她对着棉线说「果然不是香，这是什么东西」。回忆袁护士的话「老方子，睡前点一根」——现在知道那不是香。手机屏幕2:17。",
        "function_tag": "机制异常+识破", "density": "密", "budget_chars": 700,
    },
    {
        "beat_id": "b4",
        "description": "翻香盒看生产日期。对话/推断：林知夏念出声「2004年」，但包装是90年代工艺。自言自语：「2004年的东西用90年代的纸，这厂家是穿越的吗？」时间线对不上。走廊声控灯亮了——有人脚步。内心戏：「谁凌晨三点在走廊走？这楼不是说没几个住户？」推断中断。她没收香扔垃圾桶，棉线收进速写本。",
        "function_tag": "数字伏笔+推断中断", "density": "密", "budget_chars": 600,
    },
    {
        "beat_id": "b5",
        "description": "凌晨3点失眠出门。404门开缝。对话为主：黑雨衣男人说「帮个忙」，林知夏问「你是404的？」，男人不答只说「挂墙上就行」。挂完画，男人三句核心对话：你屋里点的那种叫引魂/点错位置招了不该看的过来/画挂上它就不进你屋了。内心戏：林知夏想问但门关了。看门牌404三个字写反了。",
        "function_tag": "送画+核心对话", "density": "密", "budget_chars": 700,
    },
    {
        "beat_id": "b6",
        "description": "把画搬进403。手电筒打光。内心戏：画是403卧室一模一样的构图，但床沿站着无脸人。林知夏想「谁画的？什么时候画的？」指甲碰画中无脸人位置时画纸温热——缩手。内心戏：「不对，画纸不该是温的。」不写无脸人动。",
        "function_tag": "无脸人意象第一眼", "density": "密", "budget_chars": 500,
    },
    {
        "beat_id": "b7",
        "description": "章末翻转钩。翻背板——044是颜料未干——拇指抹开——是404。内心戏推断：404被看反了。翻正面——无脸人手里线香断了。想起房东微信「404上周搬走但门口还摆着鞋子」。背板最底一行：403住户你搬进来之前404空了整整三十年。看门牌403，对面404招租启事——电话是自己刚换掉的手机号。内心戏：「这电话是我的。我昨天刚换的。没人知道。」",
        "function_tag": "章末钩·身份反转式", "density": "密", "budget_chars": 400,
    },
]


# === 七条本章伏笔 ===
FORESHADOWING_LEDGER = [
    ("袁护士手腕旧疤", "袁护士递香时手腕有一条蜈蚣样旧疤林知夏没看清就当没看清", "f1"),
    ("三厘米圆盘制式", "三厘米圆形香插市面上没有规格林知夏用尺测吻合焦痕", "f2"),
    ("1994年10月14日生产日期", "香盒底生产日期模糊过目不忘提取2004-10-14但包装是1990年代工艺", "f3"),
    ("速写本强迫擦拭", "林知夏放下手机时把手机壳在水洗被单角落擦了两下是强迫症表现", "f4"),
    ("404招租启事电话", "404门牌上贴的招租启事电话是林知夏刚换掉的手机号", "f5"),
    ("七厘米香灰是蜡壳棉线", "七厘米香灰一捏碎三块不是香是蜡壳裹红色棉线浸油脂", "f6"),
    ("404住户上周搬走", "房东说404上周搬走但404门口摆着雨天鞋子不该有人却有人", "f7"),
]


# === 写作硬约束 ===
WRITER_RULES = """【本章硬约束·必守——风格：短句口语化内心戏】
1. 限知视角锁死林知夏此刻感知。她不知道的不写。读者与主角同步获知。
2. 林知夏一律"她"。袁护士"她"。404小孩"其"或直呼"小孩"。黑雨衣男人"他"。
3. 章末钩13式之身份反转式。读者脑里必须出"那不是我以为的"不是"那是什么"。
4. 数字承载情感：12根香/3厘米/7厘米/044/404/2:17/2004-10-14/三十年/四十2个住户。每个数字都承载剧情信号，禁"很多""很久""一会儿"。
5. 三维度揉进：每个beat同时含"发生什么+林知夏注意到什么+她身体怎么回应"三层，不按层分段写。
6. 节奏一动后必静一静后可动。Beat3写完伸手触灰后必静1段呼吸再起Beat4。Beat5走廊对话后必回静一段把画搬进屋再起Beat6。
7. 对话标签<50%。全章只Beat5一处对话3句。用动作替代"男人说"——"画后传来一句闷音"。
8. 无脸人在本章只出现1次（画中）。禁止镜中、卧室、走廊二次重复。
9. 禁词：心碎/恐惧/悲伤/夙愿/宿命/天选/颤抖/浑身发冷/后背发凉/不寒而栗。用具体身体动作代替。
10. 禁标点：省略号和破折号禁用。改用句号、逗号、短句或动作断句。
11. 禁大段环境铺垫超过80字。开篇前100字必须≥3个事件（搬入/钥匙/声控灯/香）。
12. 禁情绪总结句——不许出现"她感到害怕"或"她意识到这房子不对劲"。
13. 禁止林知夏童年记忆闪回——她失忆没童年记忆可闪。
14. 禁止夹缝走廊开放。禁止无脸人动。不揭袁护士身份。不揭林知夏1994幸存者身份。
15. 用具象物证代替情绪：抽屉焦痕/圆盘吻合/香灰弯曲/颜料未干/招租启事旧号码。

【风格指令——网文写作规范】
A. 对话驱动剧情（30-40%）。对话要有互动感（打断、反问、吐槽）、功能性（给信息/造冲突/推行动）、潜台词（不直说情绪）。独处场景也要有对话（自言自语、回忆别人的话）。
B. 内心戏密集（20-30%）。主角的脑内吐槽、推断、自我怀疑。不是"她感到害怕"，而是"不是，这时间线对不上"。
C. 情绪用动作和身体反应呈现，禁用情绪词。把"脸"拆成眼睛、嘴角、眉毛写细节变化。
D. 动作拆成3-5个小动作。重要转折处加"二次动作"和"停顿节点"（伸到一半停住、递过去又缩回）。
E. 场景五感描写，穿插在动作和对话之间，不集中堆砌。景物和情绪挂钩。
F. 人物专属特征：小动作、小癖好、口头禅，形成记忆点。
G. 句子不超50字，一句话一件事。大白话，不用华丽辞藻。
H. 段落参差不齐，不规则才对。穿插小阻碍、意外转折打破平淡叙事。

【参考作品原文节奏（仅作风格参照，不复制内容）】
A. 长短句交替：「曾经一起玩游戏，一起洗澡，一起睡觉。可问题就是，随着年龄的增长，大家却渐行渐远，到后面哪怕在学校里见了面也不会打一声招呼。」三个短句加速→一个长句收束。
B. 段落参差：「她就坐在那，静静的看着书，清清冷冷，周围的时间都似乎停止了。很漂亮。白晚晚是林舟的青梅，也是同一天，同一个医院出生的。」中段→两字独段→长段。
C. 过渡自然：「"等会我们要去唱K，林舟你送晚晚回家吧。"晚饭结束之后，林父直接丢给林舟一把车钥匙。接过钥匙，林舟看了白晚晚一眼，对方默默的站在了林舟的身边。两人挨得不近不远，但林舟已经能够闻到对方身上的体香味。」场景过渡用动作连接。
D. 叙述顺滑：「林舟身体前倾，结果一只嫩白小手盖了过来，拍在了他的脸上。"看不见了——"林舟说着，白晚晚的小手冰冰凉凉的，还带着说不出的一点柔软。」动作→对话→触感，一个句子串联多个信息。
E. 内心独白融入：「"果然是垃圾软件，一点也不准！"林舟暗骂了一下重新点开那垃圾软件，却发现白晚晚的状态变了。他刚刚的确只是喊白晚晚而已，这软件是怎么听见的？」独白和叙述揉在一起。
F. 对话融入叙述：「"林舟。"在他纠结着的时候，一道细微的声音响起，让林舟抬起头。"白晚晚？怎么了……"她垂着眼眸，还是一副没有表情的样子。"晚上……家庭聚会。"白晚晚说。」对话+动作+心理混在一起。
"""


def short(s: str, n: int = 8000) -> str:
    return s if len(s) <= n else s[:n] + "...[截断]"


def main() -> int:
    out_dir = Path("qingmei_out/empty_rooms_v2")
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(out_dir / "empty_rooms_v2.db")

    if Path(db_path).exists():
        Path(db_path).unlink()
    for ext in ("-shm", "-wal"):
        p = Path(db_path + ext)
        if p.exists():
            p.unlink()

    db = Database(db_path)
    db.initialize()
    reg = SessionRuntimeStoreRegistry(db)
    engine = NovelEngine(reg)

    # 1. 项目
    print("=" * 60)
    print("【1/5】创建项目")
    print("=" * 60)
    project = NovelProject(
        project_id="empty-rooms-v2",
        title="空房间",
        genre="都市怪谈·夹缝怪谈·记忆悬疑",
        target_platform="番茄长篇",
        target_reader="22-35岁喜欢压抑悬疑与异能对抗流",
        core_emotion="压抑→怀疑→被迫接纳→主动选择",
        one_sentence_pitch=(
            "失眠三年的女插画师搬进1994年事故旧址改建的廉租房，"
            "发现房东是三十年前阿棉花计划复活的护士，"
            "她自己是漏网引魂人之一。"
        ),
        status="writing",
    )
    reg.novel_project_store.create(project)
    print("  title:", project.title)
    print("  pitch:", short(project.one_sentence_pitch, 100))

    # 2. 角色（更贴合世界观版）
    print()
    print("=" * 60)
    print("【2/5】创建角色")
    print("=" * 60)

    lin = NovelCharacter(
        character_id="char-lin",
        project_id="empty-rooms-v2",
        name="林知夏",
        aliases=("知夏",),
        role="protagonist",
        personality=(
            "28岁自由插画师。失眠三年。表象抑郁青年，实则是1994年事故5岁幸存者，"
            "记忆被父亲抹除，过目不忘是脑损伤后遗症（实为Lv.0引魂预备）。"
            "话不多心里台词密集。三年临终关怀义工经历，"
            "把病人一个个画下来再一个个送走。"
        ),
        voice_style="短句。内心独白密集，自嘲式吐槽。嘴上不说，脑子里已经转了八百个弯。失眠三年练出来的麻木外表下藏着敏锐观察力。用「行吧」「好家伙」「完了」「不是」等口语感叹。问到失眠只说「习惯了」，问到家人换话题。",
        pov_eligible=True,
        core_motivation="搞清楚每晚梦到同一栋废弃医院的原因——然后活下去。",
        weakness="分不清梦境和现实；识脸能力刚开始觉醒还不可控。",
        relationships=(
            CharacterRelationship(
                target_character_id="char-yuan",
                target_name="袁护士",
                relation_type="房东／监视者／暗助者",
                description=(
                    "搬进去见到的第一个活人，自称退休护士。"
                    "实为1960年代阿棉花计划护士，1994年事故复活。"
                    "林知夏母亲的同父异母姐姐，即林知夏姨妈。"
                    "指节凉因反魂香灼伤。第三卷揭身份。"
                ),
                tension="high",
            ),
            CharacterRelationship(
                target_character_id="char-404",
                target_name="404号住户",
                relation_type="梦的引子／童年玩伴残影",
                description=(
                    "戴白帽沉默小孩。1994年事故中死去的最年幼失踪者之一。"
                    "在夹缝中是残室意识体，阳岸出现的只是投影。"
                    "林知夏孤儿院玩伴小四。第三卷被反派召旧借体。"
                ),
                tension="medium",
            ),
            CharacterRelationship(
                target_character_id="char-404-man",
                target_name="404黑雨衣男人",
                relation_type="送画者／谜样人",
                description=(
                    "第一卷第1章登场送画，并非404真住户。"
                    "第二卷第三处旧址才再出现，暗示是民间引魂人圈层。"
                ),
                tension="medium",
            ),
        ),
        current_state={
            "identity": "失眠三年的自由插画师（深层身份未知Lv.0引魂预备）",
            "ability": "过目不忘、识脸（觉醒前）",
            "location": "刚搬进医院改建的廉租房403室",
            "emotion": "压抑、好奇、靠失眠维持的警觉",
            "gender": "女",
        },
        arc_phase="setup",
        first_appearance=1,
    )

    yuan = NovelCharacter(
        character_id="char-yuan",
        project_id="empty-rooms-v2",
        name="袁护士",
        aliases=("袁姐", "房东"),
        role="antagonist",  # 前期反派，后期同盟
        personality=(
            "表象五十岁皱纹柔和会一边和你说笑一边把灯关到只剩一盏。"
            "实质1960年代阿棉花计划护士，1994年复活被困夹缝三十年。"
            "称谓切换极快——刚叫「知夏」转头就成「那孩子」。"
            "腕有反魂香灼伤旧疤。"
        ),
        voice_style="长句。喜欢用「我跟你讲」开头，再不给对方插话的机会。",
        pov_eligible=False,
        core_motivation="照看林知夏并等待缝魂派命令——她也想完成1994年未竟之事。",
        weakness="只在林知夏失眠最严重的凌晨3点出现。她没法在清醒的人面前起作用。",
        relationships=(
            CharacterRelationship(
                target_character_id="char-lin",
                target_name="林知夏",
                relation_type="外甥女／暗助目标",
                description="1994年从火场救出5岁的林知夏送孤儿院。林知夏母亲的同父异母姐姐。",
                tension="high",
            ),
        ),
        current_state={
            "identity": "廉租房房东，深层身份是阿棉花计划护士复活体",
            "ability": "用记忆制造归属感，Lv.??未知",
            "location": "403室对面值班室",
            "emotion": "等待了三十年的耐心",
            "gender": "女",
        },
        arc_phase="setup",
        first_appearance=1,
    )

    reg.novel_character_store.save(lin)
    reg.novel_character_store.save(yuan)
    print("  主角:", lin.name, "|", lin.personality[:80], "...")
    print("  反派:", yuan.name, "|", yuan.personality[:80], "...")

    # 3. 注入世界观到 ledger
    print()
    print("=" * 60)
    print("【3/5】注入世界观到 ledger")
    print("=" * 60)

    reg.novel_ledger_store.upsert(LedgerItem(
        item_id="world-rules",
        project_id="empty-rooms-v2",
        section="world_setting",
        entity="世界观核心",
        content=WORLD_RULES,
        status="active",
        source_chapter=0,
    ))
    reg.novel_ledger_store.upsert(LedgerItem(
        item_id="writer-rules",
        project_id="empty-rooms-v2",
        section="writer_rules",
        entity="本章硬约束",
        content=WRITER_RULES,
        status="active",
        source_chapter=0,
    ))
    # 七条伏笔
    for name, content, fid in FORESHADOWING_LEDGER:
        reg.novel_ledger_store.upsert(LedgerItem(
            item_id=f"foreshadow-{fid}",
            project_id="empty-rooms-v2",
            section="foreshadowing",
            entity=name,
            content=content,
            status="planted",
            source_chapter=1,
        ))
    print(f"  ledger 注入:世界观+写作约束+{len(FORESHADOWING_LEDGER)}条伏笔")

    # 4. 手动构造 ChapterPlan（细纲驱动，不调 architect）
    print()
    print("=" * 60)
    print("【4/5】手动构造 ChapterPlan")
    print("=" * 60)

    beats = tuple(
        BeatDetail(
            beat_id=b["beat_id"],
            description=b["description"],
            function_tag=b["function_tag"],
            density=b["density"],
            budget_chars=b["budget_chars"],
        )
        for b in BEATS_DATA
    )

    plan = ChapterPlan(
        chapter_id="empty-rooms-v2-ch01",
        project_id="empty-rooms-v2",
        volume_id="",
        chapter_index=1,
        title="403室的安神香与无脸画",
        target_chars=4000,
        chapter_position="开篇钩章",
        target_emotion="压抑→怀疑→第一次识破",
 opening_hook=(
            "纸箱压得胳膊发麻。林知夏用肩膀顶开403的门，鞋底蹭掉一块墙皮。"
            "灰白色的，像蜕皮。"
            "袁护士把黄铜钥匙扔在鞋柜上。金属撞木板，闷响。"
            "「安神香，十二根，睡前点。」"
            "林知夏接过盒子，没问为什么房东会送租客香。"
            "防盗门在身后合上。锁舌弹进锁孔。"
            "咔哒。"
            "走廊的声控灯灭了。"
            "前100字必须≥3个事件：搬入/钥匙/声控灯/香。短句起笔，动作驱动。"
        ),
        main_payoff=(
            "林知夏识破安魂香是蜡壳棉线（非真香）；"
            "404男人送画中是无脸人——读者第一次见到核心意象；"
            "章末翻转：403招租启事电话是林知夏自己的旧手机号。"
        ),
        content_summary=ContentSummary(
            cause="林知夏搬入403收到袁护士的12根安神香",
            development=(
                "她测出黄铜圆盘吻合抽屉焦痕、识破香是蜡壳棉线"
                "而非粉末、走廊遇404男人送画"
            ),
            turning_point=(
                "拆画发现无脸人意象第一眼"
            ),
            climax="画框背板404是写反的044，颜料未干",
            ending=(
                "背板另一行字：403住户你搬进来之前404空了整整三十年。"
                "门外404招租启事电话是林知夏旧手机号。"
            ),
        ),
        plot_arrangement=PlotArrangement(
            main_line="林知夏搬入403并触发引魂香机制",
            sub_line="无脸人意象第一次出现",
            event_line=(
                "搬入→焦痕匹配→识破假香→送画→拆画→招租启事"
            ),
            emotion_line="压抑→好奇→识破→震惊",
            logic_line=(
                "物证链：焦痕→圆盘→包装日期→棉线→画→背板颜料→招租电话"
            ),
        ),
        character_appearance=CharacterAppearance(
            appearance_order=("林知夏", "袁护士", "404黑雨衣男人"),
            relationship_changes=(
                "袁护士→林知夏：表面房东房客，实际是30年暗中照看",
                "404男人→林知夏：送画者身份不明",
            ),
            information_gap="林知夏不知道袁护士是亲属；不知道自己1994幸存者身份",
        ),
        ending_design=EndingDesign(
            closing_state="林知夏面对404招租启事静止不动",
            open_questions=(
                "404是空还是不空？",
                "林知夏搬进来之前这间屋子里住的是谁？",
            ),
            next_chapter_push="林知夏开始追查404男人身份",
            hook_type="身份反转式",
            hook_detail=(
                "404招租启事电话是林知夏刚换掉的手机号，"
                "意味着404的招租在林知夏自己搬进来之前就贴了——"
                "招的是她。"
            ),
            hook_strength="high",
        ),
        scene_beats=beats,
        cost_and_reward="本章无显式代价；读者认知翻转是奖励",
    )

    reg.novel_chapter_plan_store.save(plan)
    print(f"  ChapterPlan已保存 chapter_id={plan.chapter_id}")
    print(f"  beats数量:{len(beats)} 目标字数:{plan.target_chars}")
    print(f"  章末钩类型:{plan.ending_design.hook_type} 强度:{plan.ending_design.hook_strength}")

    # 5. 写第1章
    print()
    print("=" * 60)
    print("【5/5】执行 write_chapter (跳过 plan_chapter)")
    print("=" * 60)

    t0 = time.time()

    def on_done(idx, draft):
        # 即时落盘
        out_file = out_dir / f"chapter_{idx:02d}.txt"
        with out_file.open("w", encoding="utf-8") as f:
            f.write(f"第{plan.chapter_index}章：{plan.title}\n")
            f.write(f"目标情绪：{plan.target_emotion}\n")
            f.write(f"章末钩：{plan.ending_design.hook_type}（{plan.ending_design.hook_strength}）\n")
            f.write("=" * 60 + "\n\n")
            f.write((draft.text or "").strip() + "\n")
        print(f"\n  📝 第{idx}章完成: {draft.char_count}字 状态={draft.status}")
        print(f"     已保存 -> {out_file}")

    try:
        draft = engine.write_chapter(
            project_id="empty-rooms-v2",
            chapter_index=1,
        )
        on_done(1, draft)
    except Exception as e:
        import traceback
        print(f"\n  ❌ 失败: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print(f"完成！用时 {elapsed:.1f}s 字数 {draft.char_count} 状态 {draft.status}")
    print("=" * 60)

    # 屏幕预览
    print()
    text = (draft.text or "").strip()
    preview_len = 1200
    print(f"--- 全文预览（前{preview_len}字）---")
    print(text[:preview_len] + ("..." if len(text) > preview_len else ""))

    return 0 if draft.text and draft.text.strip() else 1


if __name__ == "__main__":
    raise SystemExit(main())