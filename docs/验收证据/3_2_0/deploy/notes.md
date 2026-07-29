# 3.2.0 deploy live (v3 re-capture)

BASE=http://192.168.30.46 VERSION=3.2.0 account=liminghao
OUT=docs/验收证据/3_2_0/deploy
rule: kpi_ok requires 基本情况/税前利润/… + 万 AND no 正在计算 splash
login_api status=200
=== ROUND 1 ===
r1_overall wait={'ok': True, 'ms': 24}
r1_overall.png: bytes=646158 kpi_ok=True splash=False markers=['基本情况', '税前利润', '交付金额', '经营利润', '毛利率']
r1_bu_data wait={'ok': True, 'ms': 6}
r1_bu_data.png: bytes=681926 kpi_ok=True splash=False markers=['基本情况', '税前利润', '交付金额', '经营利润', '毛利率']
r1_bu_game wait={'ok': True, 'ms': 7}
r1_bu_game.png: bytes=676706 kpi_ok=True splash=False markers=['基本情况', '税前利润', '交付金额', '经营利润', '毛利率']
r1_export html=200/10188158 png=200/6127925 magic=True
=== ROUND 2 ===
r2_overall wait={'ok': True, 'ms': 28}
r2_overall.png: bytes=651855 kpi_ok=True splash=False markers=['基本情况', '税前利润', '交付金额', '经营利润', '毛利率']
r2_bu_data wait={'ok': True, 'ms': 6}
r2_bu_data.png: bytes=681771 kpi_ok=True splash=False markers=['基本情况', '税前利润', '交付金额', '经营利润', '毛利率']
r2_bu_game wait={'ok': True, 'ms': 7}
r2_bu_game.png: bytes=676602 kpi_ok=True splash=False markers=['基本情况', '税前利润', '交付金额', '经营利润', '毛利率']
r2_export html=200/10188158 png=200/6127373 magic=True
legacy_hits=0
kpi_fail_count=0
tip=5db276f VERSION=3.2.0 HEAD_MATCH=yes onbox_log=onbox_tip_match.txt
