"""Add variant_mappings table and seed from registry

Revision ID: add_variant_mappings
Revises: add_admin_panel_config
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = 'add_variant_mappings'
down_revision = 'add_admin_panel_config'
branch_labels = None
depends_on = None


def _seed_data():
    """Return list of dicts to bulk-insert into variant_mappings."""
    rows = []

    def add(category, map_type, key, data):
        rows.append(dict(category=category, map_type=map_type, key=key, data=data, is_active=True))

    # ---- Health Risks ----
    for rsid, d in {
        'rs7903146': {'condition': 'Type 2 Diabetes', 'risk_multiplier': 1.4},
        'rs9939609': {'condition': 'Obesity', 'risk_multiplier': 1.3},
        'rs1801133': {'condition': 'Cardiovascular Disease', 'risk_multiplier': 1.2},
        'rs1799944': {'condition': 'Deep Vein Thrombosis', 'risk_multiplier': 1.5},
        'rs1801282': {'condition': 'Type 2 Diabetes', 'risk_multiplier': 0.8},
        'rs662':     {'condition': "Alzheimer's Disease", 'risk_multiplier': 1.1},
        'rs429358':  {'condition': "Alzheimer's Disease", 'risk_multiplier': 3.2},
        'rs7412':    {'condition': "Alzheimer's Disease", 'risk_multiplier': 0.7},
    }.items():
        add('health', 'rsid', rsid, d)

    for gene, d in {
        'TP73':      {'condition': 'Cancer Susceptibility', 'risk_level': 'low', 'risk_score': '1.1x', 'recommendations': ['Regular cancer screenings', 'Antioxidant-rich diet', 'Avoid known carcinogens']},
        'CHD5':      {'condition': 'Tumor Suppression', 'risk_level': 'low', 'risk_score': '1.1x', 'recommendations': ['CHD5 is a chromatin remodeling tumor suppressor', 'Regular health screenings recommended', 'Maintain healthy lifestyle']},
        'MMEL1':     {'condition': 'Hypertension Risk', 'risk_level': 'moderate', 'risk_score': '1.2x', 'recommendations': ['Monitor blood pressure regularly', 'Low sodium diet', 'Regular cardiovascular exercise']},
        'RNF207':    {'condition': 'Cardiac Rhythm', 'risk_level': 'low', 'risk_score': '1.1x', 'recommendations': ['RNF207 is associated with cardiac repolarization', 'Regular ECG monitoring', 'Maintain electrolyte balance']},
        'NPHP4':     {'condition': 'Kidney Health', 'risk_level': 'low', 'risk_score': '1.1x', 'recommendations': ['Stay well hydrated', 'Regular kidney function tests', 'Balanced protein intake']},
        'PLEKHG5':   {'condition': 'Peripheral Nerve Health', 'risk_level': 'low', 'risk_score': '1.1x', 'recommendations': ['PLEKHG5 variants may affect nerve function', 'Regular neurological check-ups', 'Vitamin B12 supplementation if deficient']},
        'PARK7':     {'condition': 'Neurodegenerative Risk', 'risk_level': 'low', 'risk_score': '1.1x', 'recommendations': ['PARK7/DJ-1 protects against oxidative stress', 'Regular exercise supports brain health', 'Antioxidant-rich diet']},
        'ERRFI1':    {'condition': 'Growth Factor Regulation', 'risk_level': 'low', 'risk_score': '1.0x', 'recommendations': ['ERRFI1 regulates EGFR signaling', 'Regular health screenings', 'Balanced nutrition']},
        'TNFRSF14':  {'condition': 'Immune System Health', 'risk_level': 'low', 'risk_score': '1.1x', 'recommendations': ['TNFRSF14 mediates immune signaling', 'Maintain balanced immune function', 'Regular vaccinations and check-ups']},
        'TNFRSF9':   {'condition': 'Immune Activation', 'risk_level': 'low', 'risk_score': '1.0x', 'recommendations': ['TNFRSF9 (4-1BB) supports T-cell immunity', 'Regular immune health monitoring', 'Adequate sleep and nutrition']},
        'GNB1':      {'condition': 'Neurological Development', 'risk_level': 'low', 'risk_score': '1.1x', 'recommendations': ['GNB1 mediates G-protein signaling', 'Neuroprotective lifestyle recommended', 'Regular cognitive health assessments']},
        'RERE':      {'condition': 'Developmental Health', 'risk_level': 'low', 'risk_score': '1.0x', 'recommendations': ['RERE is a transcription regulator', 'Standard health monitoring', 'Balanced nutrition for cellular function']},
        'DFFB':      {'condition': 'DNA Damage Response', 'risk_level': 'low', 'risk_score': '1.0x', 'recommendations': ['DFFB is involved in DNA fragmentation during apoptosis', 'Minimize exposure to DNA-damaging agents', 'Adequate folate intake']},
    }.items():
        add('health', 'gene', gene, d)

    # ---- Drug Responses ----
    for rsid, d in {
        'rs1799853': {'gene': 'CYP2C9',  'drugs': ['warfarin', 'phenytoin']},
        'rs1057910': {'gene': 'CYP2C9',  'drugs': ['warfarin', 'losartan']},
        'rs1800734': {'gene': 'NAT2',    'drugs': ['isoniazid', 'hydralazine']},
        'rs4244285': {'gene': 'CYP2C19', 'drugs': ['clopidogrel', 'omeprazole']},
        'rs4680':    {'gene': 'COMT',    'drugs': ['levodopa', 'methyldopa']},
        'rs1801280': {'gene': 'NAT2',    'drugs': ['isoniazid', 'procainamide']},
    }.items():
        add('drug', 'rsid', rsid, d)

    for gene, d in {
        'PRKCZ':    {'gene': 'PRKCZ',    'drugs': [['memantine', 'normal', 'Standard dosing likely appropriate for PRKCZ variant carriers']]},
        'GABRD':    {'gene': 'GABRD',    'drugs': [['benzodiazepines', 'intermediate', 'GABRD variant may affect GABAergic drug response - monitor closely'], ['barbiturates', 'intermediate', 'Modified GABAergic signaling - standard monitoring recommended']]},
        'KCNAB2':   {'gene': 'KCNAB2',   'drugs': [['anticonvulsants', 'intermediate', 'KCNAB2 affects potassium channel subunits - monitor anticonvulsant response'], ['carbamazepine', 'normal', 'Standard potassium channel activity expected']]},
        'GNB1':     {'gene': 'GNB1',     'drugs': [['beta-blockers', 'normal', 'GNB1 mediates G-protein signaling - standard beta-blocker response expected']]},
        'PARK7':    {'gene': 'PARK7',    'drugs': [['levodopa', 'normal', 'PARK7/DJ-1 variants - standard dopaminergic drug response expected'], ['MAO-B inhibitors', 'normal', 'Standard neuroprotective drug response']]},
        'SLC45A1':  {'gene': 'SLC45A1',  'drugs': [['metformin', 'normal', 'SLC45A1 affects glucose transport - monitor glycemic response']]},
        'DVL1':     {'gene': 'DVL1',     'drugs': [['lithium', 'intermediate', 'DVL1 modulates Wnt signaling - lithium response may vary']]},
        'MMEL1':    {'gene': 'MMEL1',    'drugs': [['ACE inhibitors', 'normal', 'MMEL1 involved in peptide metabolism - standard antihypertensive response']]},
        'TNFRSF14': {'gene': 'TNFRSF14', 'drugs': [['immunotherapy', 'normal', 'TNFRSF14 mediates immune checkpoint - monitor immunotherapy response']]},
    }.items():
        add('drug', 'gene', gene, d)

    # ---- Physical Traits ----
    for rsid, d in {
        'rs1815739': {'trait': 'Fast-twitch muscle fibers', 'category': 'athletic', 'result': 'present', 'confidence': 'high'},
        'rs1800407': {'trait': 'Light eye color', 'category': 'appearance', 'result': 'predisposed', 'confidence': 'high'},
        'rs1393350': {'trait': 'Hair thickness', 'category': 'appearance', 'result': 'thick', 'confidence': 'moderate'},
        'rs4988235': {'trait': 'Lactose tolerance', 'category': 'digestive', 'result': 'tolerant', 'confidence': 'high'},
        'rs713598':  {'trait': 'Bitter taste sensitivity', 'category': 'sensory', 'result': 'sensitive', 'confidence': 'moderate'},
    }.items():
        add('physical', 'rsid', rsid, d)

    for gene, d in {
        'PRDM16': {'trait': 'Brown Fat Thermogenesis', 'category': 'metabolic', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'PRDM16 regulates brown fat cell differentiation, affecting cold tolerance and energy expenditure'},
        'TAS1R1': {'trait': 'Umami Taste Perception', 'category': 'sensory', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'TAS1R1 encodes a taste receptor affecting sensitivity to savory/umami flavors'},
        'TAS1R3': {'trait': 'Sweet Taste Perception', 'category': 'sensory', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'TAS1R3 forms part of both sweet and umami taste receptors'},
        'SKI':    {'trait': 'Muscle Development', 'category': 'athletic', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'SKI regulates muscle growth and skeletal development through TGF-\u03b2 signaling'},
        'AGRN':   {'trait': 'Neuromuscular Junction', 'category': 'athletic', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'AGRN is critical for neuromuscular junction formation and muscle-nerve communication'},
        'MEGF6':  {'trait': 'Tissue Development', 'category': 'appearance', 'result': 'variant detected', 'confidence': 'low', 'description': 'MEGF6 is involved in cell adhesion and tissue development processes'},
        'GABRD':  {'trait': 'Sensory Processing', 'category': 'sensory', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'GABRD encodes a GABA receptor subunit involved in sensory signal modulation'},
        'MMEL1':  {'trait': 'Blood Pressure Regulation', 'category': 'cardiovascular', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'MMEL1 is associated with blood pressure regulation through peptide metabolism'},
        'OR4F5':  {'trait': 'Olfactory Perception', 'category': 'sensory', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'OR4F5 encodes an olfactory receptor that contributes to sense of smell diversity'},
        'ESPN':   {'trait': 'Hair Cell Function', 'category': 'sensory', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'ESPN is essential for stereocilia development in inner ear hair cells affecting hearing'},
        'ACTRT2': {'trait': 'Hair Distribution Pattern', 'category': 'appearance', 'result': 'variant detected', 'confidence': 'low', 'description': 'ACTRT2 is an actin-related protein associated with androgenetic alopecia patterns'},
        'RNF207': {'trait': 'Heart Rate Variability', 'category': 'cardiovascular', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'RNF207 is associated with cardiac repolarization and heart rhythm patterns'},
        'CALML6': {'trait': 'Calcium Signaling', 'category': 'metabolic', 'result': 'variant detected', 'confidence': 'low', 'description': 'CALML6 is a calmodulin-like protein involved in calcium-dependent signaling'},
        'UTS2':   {'trait': 'Vascular Tone', 'category': 'cardiovascular', 'result': 'variant detected', 'confidence': 'moderate', 'description': 'UTS2 (urotensin-II) is a potent vasoconstrictor affecting blood vessel diameter'},
    }.items():
        add('physical', 'gene', gene, d)

    # ---- Nutrition ----
    for rsid, d in {
        'rs4988235': {'nutrient': 'Lactose', 'metabolism': 'lactase_persistence', 'sensitivity': 'moderate', 'recommendations': ['Monitor dairy intake', 'Consider lactose-free alternatives if symptomatic']},
        'rs713598':  {'nutrient': 'Bitter compounds', 'metabolism': 'taste_sensitivity', 'sensitivity': 'high', 'recommendations': ['May find cruciferous vegetables bitter', 'Try varied cooking methods']},
        'rs1800497': {'nutrient': 'Dopamine', 'metabolism': 'reward_sensitivity', 'sensitivity': 'moderate', 'recommendations': ['Monitor sugar and carb cravings', 'Consider protein-rich meals']},
    }.items():
        add('nutrition', 'rsid', rsid, d)

    for gene, d in {
        'TAS1R1':  {'nutrient': 'Umami/Protein Taste', 'metabolism': 'taste_perception', 'sensitivity': 'moderate', 'recommendations': ['Enhanced umami taste perception may affect protein food preferences', 'Natural affinity for protein-rich foods']},
        'TAS1R3':  {'nutrient': 'Sweet Taste Sensitivity', 'metabolism': 'taste_perception', 'sensitivity': 'moderate', 'recommendations': ['TAS1R3 variant may alter sweet taste threshold', 'Monitor sugar intake preferences', 'Use natural sweeteners']},
        'PRDM16':  {'nutrient': 'Fat Metabolism', 'metabolism': 'thermogenesis', 'sensitivity': 'moderate', 'recommendations': ['Brown fat regulation may affect caloric needs', 'Cold exposure may enhance fat burning']},
        'NADK':    {'nutrient': 'NAD+ Metabolism', 'metabolism': 'nad_synthesis', 'sensitivity': 'moderate', 'recommendations': ['NAD+ is critical for energy metabolism', 'Consider niacin-rich foods']},
        'ACOT7':   {'nutrient': 'Fatty Acid Processing', 'metabolism': 'lipid_metabolism', 'sensitivity': 'moderate', 'recommendations': ['Involved in fatty acid chain length regulation', 'Balanced omega-3/omega-6 ratio recommended']},
        'SLC45A1': {'nutrient': 'Glucose Absorption', 'metabolism': 'sugar_transport', 'sensitivity': 'moderate', 'recommendations': ['SLC45A1 affects sugar transport', 'Monitor glycemic response to meals', 'Favor complex carbohydrates']},
        'PLCH2':   {'nutrient': 'Lipid Signaling', 'metabolism': 'phospholipid_metabolism', 'sensitivity': 'low', 'recommendations': ['PLCH2 processes phosphoinositides', 'Adequate dietary fat variety supports signaling', 'Include healthy fats in diet']},
        'PANK4':   {'nutrient': 'Coenzyme A Synthesis', 'metabolism': 'vitamin_b5_pathway', 'sensitivity': 'moderate', 'recommendations': ['PANK4 is involved in CoA biosynthesis from pantothenic acid (B5)', 'Include B5-rich foods: avocado, eggs, mushrooms']},
        'RPL22':   {'nutrient': 'Protein Synthesis', 'metabolism': 'ribosomal_function', 'sensitivity': 'low', 'recommendations': ['RPL22 is a ribosomal protein for translation', 'Adequate protein intake supports ribosomal function', 'Complete amino acid profile recommended']},
    }.items():
        add('nutrition', 'gene', gene, d)

    # ---- Sports Performance ----
    for rsid, d in {
        'rs1815739': {'category': 'power', 'advantage': 'high', 'recommendations': ['Power sports', 'Sprinting', 'Weightlifting'], 'advice': 'Focus on explosive power training with plyometrics and sprints'},
        'rs4341':    {'category': 'endurance', 'advantage': 'moderate', 'recommendations': ['Distance running', 'Cycling', 'Swimming'], 'advice': 'Balanced training approach with emphasis on aerobic capacity'},
    }.items():
        add('sports', 'rsid', rsid, d)

    for gene, d in {
        'SKI':    {'category': 'muscle_development', 'advantage': 'moderate', 'recommendations': ['Strength training', 'Resistance exercises', 'Bodybuilding'], 'advice': 'SKI gene regulates muscle growth - focus on progressive overload training'},
        'AGRN':   {'category': 'neuromuscular_efficiency', 'advantage': 'moderate', 'recommendations': ['Coordination sports', 'Martial arts', 'Team sports', 'Gymnastics'], 'advice': 'AGRN affects neuromuscular junction - train coordination and reaction time'},
        'PRDM16': {'category': 'endurance_metabolism', 'advantage': 'moderate', 'recommendations': ['Endurance sports', 'Cold-weather activities', 'Long-distance running'], 'advice': 'PRDM16 regulates brown fat thermogenesis - may benefit from cold-adapted training'},
        'KCNAB2': {'category': 'neural_signaling', 'advantage': 'moderate', 'recommendations': ['Precision sports', 'Archery', 'Shooting', 'Golf'], 'advice': 'KCNAB2 affects potassium channels in neurons - may enhance fine motor control'},
        'CAMTA1': {'category': 'neural_adaptation', 'advantage': 'moderate', 'recommendations': ['Skill-based sports', 'Tennis', 'Fencing', 'Table tennis'], 'advice': 'CAMTA1 supports memory and learning - sports with complex skill acquisition'},
        'MEGF6':  {'category': 'recovery_capacity', 'advantage': 'moderate', 'recommendations': ['High-volume training', 'CrossFit', 'Swimming'], 'advice': 'MEGF6 affects tissue development - focus on recovery protocols'},
        'ESPN':   {'category': 'balance_coordination', 'advantage': 'moderate', 'recommendations': ['Balance sports', 'Surfing', 'Skating', 'Snowboarding'], 'advice': 'ESPN affects inner ear hair cells - vestibular system may influence balance'},
        'UTS2':   {'category': 'cardiovascular_performance', 'advantage': 'moderate', 'recommendations': ['Cardio sports', 'Running', 'Cycling', 'Rowing'], 'advice': 'UTS2 affects vascular tone - cardiovascular training may be particularly effective'},
    }.items():
        add('sports', 'gene', gene, d)

    # ---- Cognitive Profiles ----
    for rsid, d in {
        'rs4680':  {'domain': 'Working Memory', 'score': 'above_average', 'percentile': 72, 'suggestions': ['Memory training exercises', 'Mindfulness meditation']},
        'rs53576': {'domain': 'Social Cognition', 'score': 'high', 'percentile': 78, 'suggestions': ['Leverage social intelligence', 'Group-based learning']},
        'rs6265':  {'domain': 'Neuroplasticity', 'score': 'average', 'percentile': 55, 'suggestions': ['Regular physical exercise', 'Novel learning activities']},
    }.items():
        add('cognitive', 'rsid', rsid, d)

    for gene, d in {
        'CAMTA1':  {'domain': 'Memory Formation', 'score': 'variant_detected', 'percentile': 60, 'suggestions': ['CAMTA1 is involved in memory consolidation', 'Regular sleep supports memory processes', 'Spaced repetition learning']},
        'CHD5':    {'domain': 'Chromatin Remodeling & Learning', 'score': 'variant_detected', 'percentile': 62, 'suggestions': ['CHD5 regulates gene expression in neurons', 'Enriched environments enhance cognitive function', 'Diverse intellectual stimulation']},
        'GNB1':    {'domain': 'Neural Signal Transduction', 'score': 'variant_detected', 'percentile': 58, 'suggestions': ['GNB1 mediates G-protein signaling in the brain', 'Adequate omega-3 intake supports neuronal function', 'Regular aerobic exercise']},
        'KCNAB2':  {'domain': 'Processing Speed', 'score': 'variant_detected', 'percentile': 65, 'suggestions': ['KCNAB2 regulates potassium channels in neurons', 'Speed-based cognitive games', 'Adequate sleep for neural efficiency']},
        'NPHP4':   {'domain': 'Sensory-Cognitive Integration', 'score': 'variant_detected', 'percentile': 55, 'suggestions': ['NPHP4 affects ciliary signaling pathways', 'Multi-sensory learning approaches', 'Visual-spatial exercises']},
        'TP73':    {'domain': 'Neural Development', 'score': 'variant_detected', 'percentile': 60, 'suggestions': ['TP73 supports neuron survival and differentiation', 'Neuroprotective lifestyle choices', 'Regular cognitive challenges']},
        'PRKCZ':   {'domain': 'Long-term Memory', 'score': 'variant_detected', 'percentile': 68, 'suggestions': ['PRKCZ (PKM\u03b6) is key for memory persistence', 'Repetition-based learning', 'Adequate protein intake supports memory']},
        'PARK7':   {'domain': 'Neuroprotection', 'score': 'variant_detected', 'percentile': 63, 'suggestions': ['PARK7/DJ-1 protects neurons from oxidative stress', 'Antioxidant-rich diet', 'Regular physical exercise supports brain function']},
        'DVL1':    {'domain': 'Neural Patterning', 'score': 'variant_detected', 'percentile': 57, 'suggestions': ['DVL1 drives Wnt signaling in brain development', 'Novel learning activities', 'Engage in creative problem-solving']},
        'GABRD':   {'domain': 'Attention & Focus', 'score': 'variant_detected', 'percentile': 60, 'suggestions': ['GABRD modulates inhibitory neurotransmission', 'Mindfulness practice enhances focus', 'Structured work sessions']},
        'PLCH2':   {'domain': 'Cognitive Flexibility', 'score': 'variant_detected', 'percentile': 56, 'suggestions': ['PLCH2 is involved in neuronal lipid signaling', 'Practice task-switching exercises', 'Diverse learning activities']},
        'DNAJC11': {'domain': 'Mitochondrial Brain Function', 'score': 'variant_detected', 'percentile': 55, 'suggestions': ['DNAJC11 supports mitochondrial membrane organization', 'Exercise boosts brain mitochondria', 'CoQ10-rich foods support energy']},
    }.items():
        add('cognitive', 'gene', gene, d)

    # ---- Personality Traits ----
    for rsid, d in {
        'rs53576':   {'trait': 'Empathy', 'tendency': 'high', 'confidence': 'high', 'insights': ['Strong empathic responses', 'Natural social bonding', 'High emotional attunement']},
        'rs4680':    {'trait': 'Stress Sensitivity', 'tendency': 'moderate', 'confidence': 'high', 'insights': ['Moderate stress response', 'Benefit from stress management techniques', 'Balanced dopamine processing']},
        'rs1800955': {'trait': 'Novelty Seeking', 'tendency': 'moderate', 'confidence': 'moderate', 'insights': ['Moderate novelty seeking', 'Balanced risk assessment']},
    }.items():
        add('personality', 'rsid', rsid, d)

    for gene, d in {
        'GABRD':  {'trait': 'Emotional Regulation', 'tendency': 'moderate', 'confidence': 'moderate', 'insights': ['GABRD modulates inhibitory neurotransmission', 'May influence anxiety response', 'Relaxation techniques beneficial']},
        'CAMTA1': {'trait': 'Conscientiousness', 'tendency': 'moderate', 'confidence': 'moderate', 'insights': ['CAMTA1 affects transcription regulation in brain', 'Associated with attention and focus', 'Structured routines may enhance natural tendencies']},
        'PLCH2':  {'trait': 'Openness to Experience', 'tendency': 'moderate', 'confidence': 'low', 'insights': ['PLCH2 is involved in phospholipase C signaling in the brain', 'May affect neural plasticity', 'Cognitive flexibility exercises recommended']},
        'PER3':   {'trait': 'Chronotype & Mood', 'tendency': 'variant_detected', 'confidence': 'moderate', 'insights': ['PER3 is a core circadian clock gene', 'Influences sleep/wake preferences and mood patterns', 'Consistent sleep schedule supports wellbeing']},
        'PRKCZ':  {'trait': 'Resilience', 'tendency': 'moderate', 'confidence': 'moderate', 'insights': ['PRKCZ supports long-term potentiation in the brain', 'Associated with stress adaptation', 'Mindfulness practices enhance resilience']},
        'GNB1':   {'trait': 'Reward Sensitivity', 'tendency': 'moderate', 'confidence': 'low', 'insights': ['GNB1 modulates dopamine signaling pathways', 'May influence reward-seeking behavior', 'Balanced reward systems through varied activities']},
        'DVL1':   {'trait': 'Social Behavior', 'tendency': 'moderate', 'confidence': 'low', 'insights': ['DVL1 Wnt signaling influences brain connectivity', 'May affect social cognition patterns', 'Social engagement supports neural health']},
        'PARK7':  {'trait': 'Stress Tolerance', 'tendency': 'moderate', 'confidence': 'moderate', 'insights': ['PARK7/DJ-1 protects against oxidative stress', 'Oxidative stress levels influence mood', 'Antioxidant diet supports emotional balance']},
        'HES5':   {'trait': 'Adaptability', 'tendency': 'moderate', 'confidence': 'low', 'insights': ['HES5 regulates neural stem cell maintenance', 'Associated with neural plasticity', 'New experiences support cognitive adaptability']},
    }.items():
        add('personality', 'gene', gene, d)

    # ---- Wellness Metrics ----
    for rsid, d in {
        'rs1801133': {'metric': 'Inflammation Response', 'predisposition': 'elevated', 'score': '65', 'recommendations': ['Anti-inflammatory diet', 'Regular exercise', 'Omega-3 supplementation']},
        'rs4680':    {'metric': 'Stress Response', 'predisposition': 'sensitive', 'score': '60', 'recommendations': ['Stress management techniques', 'Regular meditation', 'Adequate sleep']},
    }.items():
        add('wellness', 'rsid', rsid, d)

    for gene, d in {
        'PER3':     {'metric': 'Sleep Quality & Circadian Rhythm', 'predisposition': 'variant_detected', 'score': '70', 'recommendations': ['PER3 regulates circadian rhythm', 'Maintain consistent sleep schedule', 'Limit blue light exposure before bed', 'Morning light exposure recommended']},
        'PRDM16':   {'metric': 'Thermogenesis & Energy Balance', 'predisposition': 'variant_detected', 'score': '65', 'recommendations': ['PRDM16 regulates brown fat activation', 'Cold exposure may boost metabolism', 'Regular physical activity enhances brown fat function']},
        'TP73':     {'metric': 'Cellular Health & Aging', 'predisposition': 'variant_detected', 'score': '60', 'recommendations': ['TP73 family supports cellular quality control', 'Antioxidant-rich diet recommended', 'Regular health screenings', 'Avoid excessive UV exposure']},
        'DFFB':     {'metric': 'DNA Repair & Maintenance', 'predisposition': 'variant_detected', 'score': '65', 'recommendations': ['DFFB is involved in DNA fragmentation and repair', 'Adequate folate and B12 intake', 'Minimize exposure to DNA-damaging agents']},
        'ERRFI1':   {'metric': 'Growth Factor Regulation', 'predisposition': 'variant_detected', 'score': '68', 'recommendations': ['ERRFI1 regulates EGFR signaling', 'Balanced nutrition supports cellular signaling', 'Regular exercise maintains healthy growth factor levels']},
        'NADK':     {'metric': 'NAD+ & Cellular Energy', 'predisposition': 'variant_detected', 'score': '62', 'recommendations': ['NADK phosphorylates NAD+ to NADP+', 'Niacin-rich foods support NAD+ levels', 'Regular exercise boosts cellular energy metabolism']},
        'PARK7':    {'metric': 'Oxidative Stress Defense', 'predisposition': 'variant_detected', 'score': '67', 'recommendations': ['PARK7/DJ-1 is a key antioxidant sensor', 'Berries and green leafy vegetables support antioxidant defense', 'Regular exercise reduces oxidative stress']},
        'TNFRSF14': {'metric': 'Immune Balance', 'predisposition': 'variant_detected', 'score': '63', 'recommendations': ['TNFRSF14 mediates immune homeostasis', 'Balanced diet supports immune function', 'Adequate vitamin D and zinc intake']},
        'CCNL2':    {'metric': 'Cell Cycle Regulation', 'predisposition': 'variant_detected', 'score': '60', 'recommendations': ['CCNL2 is a cyclin involved in RNA processing', 'Adequate sleep supports cell cycle processes', 'Balanced nutrition for cellular renewal']},
        'DNAJC11':  {'metric': 'Mitochondrial Health', 'predisposition': 'variant_detected', 'score': '64', 'recommendations': ['DNAJC11 supports mitochondrial membrane integrity', 'CoQ10-rich foods support mitochondria', 'Regular aerobic exercise boosts mitochondrial biogenesis']},
    }.items():
        add('wellness', 'gene', gene, d)

    # ---- Methylation Profiles ----
    for rsid, d in {
        'rs1801133': {'gene': 'MTHFR', 'capacity': 'reduced', 'supplements': ['Methylfolate', 'B12', 'Riboflavin']},
        'rs1801131': {'gene': 'MTHFR', 'capacity': 'mildly_reduced', 'supplements': ['Methylfolate', 'B-complex']},
        'rs4680':    {'gene': 'COMT',  'capacity': 'slow_processing', 'supplements': ['Magnesium', 'SAM-e']},
        'rs1805087': {'gene': 'MTR',   'capacity': 'b12_dependent', 'supplements': ['Methylcobalamin', 'Folate']},
        'rs1801394': {'gene': 'MTRR',  'capacity': 'b12_dependent', 'supplements': ['Methylcobalamin', 'Folate']},
    }.items():
        add('methylation', 'rsid', rsid, d)

    for gene, d in {
        'NADK':   {'gene': 'NADK',   'capacity': 'variant_detected', 'supplements': ['NADK affects NADP+ synthesis which supports methylation cofactors', 'Niacin (B3) supports NAD+/NADP+ balance', 'B-complex vitamins']},
        'PARK7':  {'gene': 'PARK7',  'capacity': 'variant_detected', 'supplements': ['PARK7/DJ-1 supports oxidative methylation processes', 'Glutathione precursors (NAC)', 'Riboflavin (B2) supports redox cycling']},
        'PRDM16': {'gene': 'PRDM16', 'capacity': 'variant_detected', 'supplements': ['PRDM16 is a histone methyltransferase regulator', 'Methyl donors: folate, B12, betaine', 'SAM-e supports methylation pathways']},
        'PRKCZ':  {'gene': 'PRKCZ',  'capacity': 'variant_detected', 'supplements': ['PRKCZ participates in cellular methylation signaling', 'Choline supports methylation', 'B-complex vitamins recommended']},
        'CHD5':   {'gene': 'CHD5',   'capacity': 'variant_detected', 'supplements': ['CHD5 reads methylated histones for gene regulation', 'Folate and B12 support epigenetic processes', 'Green leafy vegetables provide methylation nutrients']},
    }.items():
        add('methylation', 'gene', gene, d)

    # ---- Detoxification Profiles ----
    for rsid, d in {
        'rs1799853': {'phase': 'phase1', 'gene': 'CYP2C9',  'capacity': 'reduced', 'sensitivity': 'moderate', 'recommendations': ['Monitor warfarin dosing', 'Liver function tests']},
        'rs4244285': {'phase': 'phase1', 'gene': 'CYP2C19', 'capacity': 'poor', 'sensitivity': 'high', 'recommendations': ['Avoid CYP2C19-dependent drugs', 'Genetic counseling for medication']},
    }.items():
        add('detox', 'rsid', rsid, d)

    for gene, d in {
        'PEX10': {'phase': 'peroxisomal', 'gene': 'PEX10', 'capacity': 'variant_detected', 'sensitivity': 'moderate', 'recommendations': ['PEX10 is involved in peroxisome assembly', 'Supports fatty acid oxidation and detox', 'Maintain liver health through balanced diet']},
        'ICMT':  {'phase': 'phase2', 'gene': 'ICMT', 'capacity': 'variant_detected', 'sensitivity': 'low', 'recommendations': ['ICMT methylates prenylated proteins', 'Supports post-translational protein processing', 'Adequate methyl donor intake recommended']},
        'ACOT7': {'phase': 'phase1', 'gene': 'ACOT7', 'capacity': 'variant_detected', 'sensitivity': 'moderate', 'recommendations': ['ACOT7 hydrolyzes fatty acyl-CoA thioesters', 'Supports lipid detoxification pathways', 'Balanced dietary fat intake']},
        'PANK4': {'phase': 'coenzyme_a', 'gene': 'PANK4', 'capacity': 'variant_detected', 'sensitivity': 'low', 'recommendations': ['PANK4 is involved in coenzyme A biosynthesis', 'CoA is essential for phase 2 detoxification', 'Pantothenic acid (B5) rich foods recommended']},
        'PARK7': {'phase': 'antioxidant', 'gene': 'PARK7', 'capacity': 'variant_detected', 'sensitivity': 'moderate', 'recommendations': ['PARK7/DJ-1 is a key oxidative stress sensor', 'Supports glutathione recycling', 'Cruciferous vegetables enhance detox pathways']},
        'NADK':  {'phase': 'phase1', 'gene': 'NADK', 'capacity': 'variant_detected', 'sensitivity': 'low', 'recommendations': ['NADK produces NADP+ needed for phase 1 oxidation reactions', 'Niacin supports detox enzyme activity', 'Adequate hydration aids detoxification']},
    }.items():
        add('detox', 'gene', gene, d)

    # ---- Carrier Status ----
    for rsid, d in {
        'rs334':     {'condition': 'Sickle Cell Disease', 'status': 'non-carrier'},
        'rs5030868': {'condition': 'Cystic Fibrosis', 'status': 'non-carrier'},
    }.items():
        add('carrier', 'rsid', rsid, d)

    return rows


def upgrade():
    op.create_table(
        'variant_mappings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('category', sa.String(), nullable=False, index=True),
        sa.Column('map_type', sa.String(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('data', JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )
    op.create_index(
        'ix_variant_mappings_cat_type_key',
        'variant_mappings',
        ['category', 'map_type', 'key'],
        unique=True,
    )

    # Seed all current registry data
    table = sa.table(
        'variant_mappings',
        sa.column('category', sa.String),
        sa.column('map_type', sa.String),
        sa.column('key', sa.String),
        sa.column('data', JSON),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(table, _seed_data())


def downgrade():
    op.drop_table('variant_mappings')
