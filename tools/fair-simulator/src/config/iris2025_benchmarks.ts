// src/config/iris2025_benchmarks.ts

import irisJson from '../../shared/iris2025_benchmarks.json';

export interface LEFBenchmark {
  probability: number;
  range?: [number, number];
  confidence: 'high' | 'medium' | 'low';
  source: string;
  trend?: string;
  description: string;
}

export interface LMBenchmark {
  median: number;
  p95: number;
  confidence: 'high' | 'medium' | 'low';
  source: string;
  trend?: string;
  description: string;
  sample_size?: string;
}

export interface BenchmarkMetadata {
  source: string;
  data_period: string;
  dataset_size: string;
  currency: string;
  report_date: string;
}

interface RawBenchmarksFile {
  metadata: BenchmarkMetadata;
  lef_by_industry: Record<string, LEFBenchmark>;
  lef_by_revenue: Record<string, LEFBenchmark>;
  lm_by_industry: Record<string, LMBenchmark>;
  lm_by_revenue: Record<string, LMBenchmark>;
  lef_overall_baseline: LEFBenchmark;
  lm_overall_baseline: LMBenchmark;
}

// IMPORTANT: go through `unknown` so TS doesn’t try to structurally compare
const iris = irisJson as unknown as RawBenchmarksFile;

export const IRIS_2025_METADATA: BenchmarkMetadata = iris.metadata;

export const LEF_BY_INDUSTRY: Record<string, LEFBenchmark> =
  iris.lef_by_industry;

export const LEF_BY_REVENUE: Record<string, LEFBenchmark> =
  iris.lef_by_revenue;

export const LM_BY_INDUSTRY: Record<string, LMBenchmark> =
  iris.lm_by_industry;

export const LM_BY_REVENUE: Record<string, LMBenchmark> =
  iris.lm_by_revenue;

export const LEF_OVERALL_BASELINE: LEFBenchmark = iris.lef_overall_baseline;

export const LM_OVERALL_BASELINE: LMBenchmark = iris.lm_overall_baseline;

export function getLEFBenchmark(industry?: string, revenueTier?: string) {
  const data: {
    industry?: LEFBenchmark;
    revenue?: LEFBenchmark;
    overall_baseline: LEFBenchmark;
  } = {
    overall_baseline: LEF_OVERALL_BASELINE,
  };

  if (industry && LEF_BY_INDUSTRY[industry]) {
    data.industry = LEF_BY_INDUSTRY[industry];
  }

  if (revenueTier && LEF_BY_REVENUE[revenueTier]) {
    data.revenue = LEF_BY_REVENUE[revenueTier];
  }

  return {
    success: true,
    data,
    metadata: IRIS_2025_METADATA,
  };
}

export function getLMBenchmark(industry?: string, revenueTier?: string) {
  const data: {
    industry?: LMBenchmark;
    revenue?: LMBenchmark;
    overall_baseline: LMBenchmark;
  } = {
    overall_baseline: LM_OVERALL_BASELINE,
  };

  if (industry && LM_BY_INDUSTRY[industry]) {
    data.industry = LM_BY_INDUSTRY[industry];
  }

  if (revenueTier && LM_BY_REVENUE[revenueTier]) {
    data.revenue = LM_BY_REVENUE[revenueTier];
  }

  return {
    success: true,
    data,
    metadata: IRIS_2025_METADATA,
  };
}