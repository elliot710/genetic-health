# Additional data queries to add to dashboard-data endpoint

        # Get personality traits for all analyses
        all_personality_traits = []
        for analysis in analyses:
            personality_result = await db.execute(
                select(PersonalityTrait).where(PersonalityTrait.analysis_id == analysis.id)
            )
            personality_traits = personality_result.scalars().all()
            all_personality_traits.extend(personality_traits)
        
        # Get wellness metrics for all analyses
        all_wellness_metrics = []
        for analysis in analyses:
            wellness_result = await db.execute(
                select(WellnessMetric).where(WellnessMetric.analysis_id == analysis.id)
            )
            wellness_metrics = wellness_result.scalars().all()
            all_wellness_metrics.extend(wellness_metrics)
        
        # Get physical traits for all analyses
        all_physical_traits = []
        for analysis in analyses:
            physical_result = await db.execute(
                select(PhysicalTrait).where(PhysicalTrait.analysis_id == analysis.id)
            )
            physical_traits = physical_result.scalars().all()
            all_physical_traits.extend(physical_traits)
        
        # Get nutrition traits for all analyses
        all_nutrition_traits = []
        for analysis in analyses:
            nutrition_result = await db.execute(
                select(NutritionTrait).where(NutritionTrait.analysis_id == analysis.id)
            )
            nutrition_traits = nutrition_result.scalars().all()
            all_nutrition_traits.extend(nutrition_traits)
        
        # Get sports performance for all analyses
        all_sports_performance = []
        for analysis in analyses:
            sports_result = await db.execute(
                select(SportsPerformance).where(SportsPerformance.analysis_id == analysis.id)
            )
            sports_performance = sports_result.scalars().all()
            all_sports_performance.extend(sports_performance)
        
        # Get cognitive profiles for all analyses
        all_cognitive_profiles = []
        for analysis in analyses:
            cognitive_result = await db.execute(
                select(CognitiveProfile).where(CognitiveProfile.analysis_id == analysis.id)
            )
            cognitive_profiles = cognitive_result.scalars().all()
            all_cognitive_profiles.extend(cognitive_profiles)