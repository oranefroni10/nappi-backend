"""Calculates optimal environmental conditions per baby from weighted daily summaries."""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .babies_data import BabyDataManager

logger = logging.getLogger(__name__)


@dataclass
class OptimalStatsResult:
    baby_id: int
    stats_id: Optional[int]
    temperature: Optional[float]
    humidity: Optional[float]
    noise: Optional[float]
    days_analyzed: int
    success: bool
    error: Optional[str] = None


# Used by: calculate_optimal_stats() (weights each day by inverse of total awakenings)
def calculate_weight(
    morning_awakes: int,
    noon_awakes: int,
    night_awakes: int
) -> float:
    """Weight = 1/(1+total_awakenings); 0 awakes → 1.0, 1 → 0.5, 2 → 0.33, etc."""
    total_awakes = (morning_awakes or 0) + (noon_awakes or 0) + (night_awakes or 0)
    return 1.0 / (1.0 + total_awakes)


# Used by: calculate_optimal_stats() (computes weighted avg for temp/humidity/noise)
def calculate_weighted_average(
    values: List[float],
    weights: List[float]
) -> Optional[float]:
    """Σ(value×weight)/Σ(weight)."""
    if not values or not weights or len(values) != len(weights):
        return None

    # Filter out None values and their corresponding weights
    valid_pairs = [
        (v, w) for v, w in zip(values, weights)
        if v is not None and w is not None
    ]

    if not valid_pairs:
        return None

    total_weighted = sum(v * w for v, w in valid_pairs)
    total_weight = sum(w for _, w in valid_pairs)

    if total_weight == 0:
        return None

    return round(total_weighted / total_weight, 2)


# Used by: run_optimal_stats_job() (calculates optimal stats for a single baby)
async def calculate_optimal_stats(baby_id: int) -> OptimalStatsResult:
    """Weighted averages where weight ∝ 1/awakenings (fewer awakenings = higher weight)."""
    logger.info(f"Calculating optimal stats for baby {baby_id}")

    baby_manager = BabyDataManager()

    try:
        summaries = await baby_manager.get_all_daily_summaries(baby_id)

        if not summaries:
            logger.warning(f"No daily summaries found for baby {baby_id}")
            return OptimalStatsResult(
                baby_id=baby_id,
                stats_id=None,
                temperature=None,
                humidity=None,
                noise=None,

                days_analyzed=0,
                success=False,
                error="No historical data available"
            )

        logger.info(f"Found {len(summaries)} daily summaries for baby {baby_id}")

        weights = []
        temps = []
        humidities = []
        noises = []

        for summary in summaries:
            weight = calculate_weight(
                morning_awakes=summary.get("morning_awakes_sum") or 0,
                noon_awakes=summary.get("noon_awakes_sum") or 0,
                night_awakes=summary.get("night_awakes_sum") or 0
            )
            weights.append(weight)
            temps.append(summary.get("avg_temp"))
            humidities.append(summary.get("avg_humidity"))
            noises.append(summary.get("avg_noise"))

        optimal_temp = calculate_weighted_average(temps, weights)
        optimal_humidity = calculate_weighted_average(humidities, weights)
        optimal_noise = calculate_weighted_average(noises, weights)

        logger.info(
            f"Calculated optimal stats for baby {baby_id}: "
            f"temp={optimal_temp}, humidity={optimal_humidity}, noise={optimal_noise}"
        )

        stats_id = await baby_manager.upsert_optimal_stats(
            baby_id=baby_id,
            temperature=optimal_temp,
            humidity=optimal_humidity,
            noise=optimal_noise
        )

        if stats_id is None:
            return OptimalStatsResult(
                baby_id=baby_id,
                stats_id=None,
                temperature=optimal_temp,
                humidity=optimal_humidity,
                noise=optimal_noise,

                days_analyzed=len(summaries),
                success=False,
                error="Failed to save optimal stats"
            )

        return OptimalStatsResult(
            baby_id=baby_id,
            stats_id=stats_id,
            temperature=optimal_temp,
            humidity=optimal_humidity,
            noise=optimal_noise,
            days_analyzed=len(summaries),
            success=True
        )

    except Exception as e:
        logger.error(f"Error calculating optimal stats for baby {baby_id}: {e}", exc_info=True)
        return OptimalStatsResult(
            baby_id=baby_id,
            stats_id=None,
            temperature=None,
            humidity=None,
            noise=None,
            days_analyzed=0,
            success=False,
            error=str(e)
        )


# Used by: scheduler.py (CronTrigger at 10:05 AM Israel time, after daily summary)
async def run_optimal_stats_job() -> Dict[str, Any]:
    """Calculate optimal stats for all babies (runs after daily summary job)."""
    logger.info("=" * 60)
    logger.info("Starting optimal stats calculation job")
    logger.info("=" * 60)

    baby_manager = BabyDataManager()

    try:
        babies = await baby_manager.get_babies_list()

        if not babies:
            logger.warning("No babies found in database")
            return {
                "success": True,
                "babies_processed": 0,
                "results": []
            }

        logger.info(f"Processing {len(babies)} babies")

        results = []
        success_count = 0

        for baby in babies:
            result = await calculate_optimal_stats(baby.id)

            results.append({
                "baby_id": baby.id,
                "baby_name": baby.first_name,
                "success": result.success,
                "stats_id": result.stats_id,
                "days_analyzed": result.days_analyzed,
                "optimal_temperature": result.temperature,
                "optimal_humidity": result.humidity,
                "optimal_noise": result.noise,
                "error": result.error
            })

            if result.success:
                success_count += 1

        logger.info("=" * 60)
        logger.info(
            f"Optimal stats job complete: {success_count}/{len(babies)} babies processed successfully"
        )
        logger.info("=" * 60)

        return {
            "success": True,
            "babies_processed": len(babies),
            "babies_succeeded": success_count,
            "results": results
        }

    except Exception as e:
        logger.error(f"Fatal error in optimal stats job: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "results": []
        }
