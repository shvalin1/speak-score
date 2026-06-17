"""パイプライン orchestration。各stepで repo.update_stage を逐次更新。

現状は **Walking Skeleton 雛形**: 各サービスはダミー値を返し、worker→Firestore→poll の
配線が一周することを優先する（§7 順序1b）。Step2 で各サービスの中身を流し込む。
設計根拠: design_review_and_frontback.md §2, §5.1
"""

from __future__ import annotations

import asyncio

from ..repositories.job_repo import JobRepository
from ..schemas.interview import (
    AnalysisResult,
    Dimension,
    Dimensions,
    DimensionSource,
    ProcessingStage,
)
from . import audio_analysis, llm_evaluation, scoring, transcription


async def run_pipeline(job_id: str, repo: JobRepository, worker_id: str) -> AnalysisResult:
    # stage=extracting_audio はリース取得時にセット済み。FLAC抽出は Step2。
    repo.renew_lease(job_id, worker_id)
    flac_path = ""  # TODO(Step2): storage.download_to_tmp → ffmpeg で FLAC 抽出
    await asyncio.sleep(0)  # yield

    repo.update_stage(job_id, ProcessingStage.transcribing)
    repo.renew_lease(job_id, worker_id)
    transcript = await transcription.transcribe(flac_path)

    repo.update_stage(job_id, ProcessingStage.analyzing_audio)
    repo.renew_lease(job_id, worker_id)
    metrics = audio_analysis.analyze_audio(flac_path, transcript)

    repo.update_stage(job_id, ProcessingStage.evaluating)
    repo.renew_lease(job_id, worker_id)
    llm = await llm_evaluation.evaluate(transcript, metrics)

    # 算出系（delivery/confidence）は決定論スコアリング、LLM系はllmの採点を使う
    dimensions = Dimensions(
        content=llm.content,
        structure=llm.structure,
        delivery=Dimension(
            score=scoring.score_delivery(metrics),
            comment="話速・フィラー率・無音率から算出。",
            source=DimensionSource.computed,
        ),
        confidence=Dimension(
            score=scoring.score_confidence(metrics),
            comment="音量安定性とピッチ変動から算出。",
            source=DimensionSource.computed,
        ),
    )
    return AnalysisResult(
        overall_score=scoring.overall(dimensions),
        dimensions=dimensions,
        audio_metrics=metrics,
        transcript=transcript,
        strengths=llm.strengths,
        improvements=llm.improvements,
    )
