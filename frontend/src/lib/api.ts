/* ================================================================
   API Client — typed fetch wrappers for the FastAPI backend
   ================================================================ */

import type {
  SystemStats,
  JobControlResponse,
  JobSnapshot,
  FetchPDBRequest,
  FetchPDBResponse,
  UniprotInfo,
  DrugInfo,
  PocketAnalysisRequest,
  PocketAnalysisResponse,
  GridBox,
  GridBoxResponse,
  BatchRequest,
  BatchResponse,
  MinimizeRequest,
  MinimizeResponse,
  ConvertRequest,
  ConvertResponse,
  PipelineRequest,
  PipelineResponse,
  SimilarityRequest,
  SimilarityResponse,
  DockingRequest,
  DockingResponse,
  AutoGridRequest,
  OracleRequest,
  OracleResponse,
  LoadResultsResponse,
  ExportTopRequest,
  CSVReportRequest,
  CSVReportResponse,
  FilterRequest,
  FilterResponse,
  ADMETRequest,
  ADMETResponse,
  InteractionRequest,
  InteractionResponse,
  ClusterRequest,
  ClusterResponse,
  AnalogRequest,
  AnalogResponse,
  ConsensusRequest,
  ConsensusResponse,
  DruggabilityRequest,
  DruggabilityResponse,
  PoseDecompRequest,
  PoseDecompResponse,
  Project,
  WatchlistItem,
  BatchPipelineRequest,
  BatchPipelineResponse,
  IUPACResponse,
  ResolveRequest,
  ResolveResponse,
  PrepareReceptorRequest,
  PrepareReceptorResponse,
  PDBAnalysis,
  CompareRequest,
  CompareResponse,
  PharmGenerateRequest,
  PharmGenerateResponse,
  PharmScreenRequest,
  PharmScreenResponse,
  PharmSaveRequest,
  PharmSaveResponse,
  PharmLoadResponse,
  ReportRequest,
  ReportResponse,
  FragmentDecomposeRequest,
  FragmentDecomposeResponse,
  FragmentLinkRequest,
  FragmentLinkResponse,
  FragmentGrowRequest,
  FragmentGrowResponse,
  FragmentLibraryResponse,
  MultiTargetRequest,
  MultiTargetResponse,
  ScaffoldHopRequest,
  ScaffoldHopResponse,
} from '@/types/api'

const BASE_URL = 'http://127.0.0.1:8299'

/* ---- Generic helpers ---- */

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { signal })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `GET ${path} failed (${res.status})`)
  }
  return res.json()
}

async function post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `POST ${path} failed (${res.status})`)
  }
  return res.json()
}

/* ---- System ---- */
export const getSystemStats = () => get<SystemStats>('/api/system/stats')

/* ---- Global Jobs ---- */
export const getCurrentJob = () =>
  get<JobSnapshot | null>('/api/jobs/current')

export const pauseJob = (jobId: string) =>
  post<JobControlResponse>(`/api/jobs/${jobId}/pause`, {})

export const resumeJob = (jobId: string) =>
  post<JobControlResponse>(`/api/jobs/${jobId}/resume`, {})

export const terminateJob = (jobId: string) =>
  post<JobControlResponse>(`/api/jobs/${jobId}/terminate`, {})

/* ---- PDB Fetch ---- */
export const fetchPDB = (data: FetchPDBRequest) =>
  post<FetchPDBResponse>('/api/fetch/pdb', data)

export const getUniprotInfo = (pdbId: string) =>
  get<UniprotInfo>(`/api/fetch/uniprot/${pdbId}`)

export const findDrugControls = (pdbId: string) =>
  get<DrugInfo | null>(`/api/fetch/controls/${pdbId}`)

/* ---- Pocket ---- */
export const analyzePocket = (data: PocketAnalysisRequest) =>
  post<PocketAnalysisResponse>('/api/pocket/analyze', data)

export const calculateGrid = (data: PocketAnalysisRequest) =>
  post<GridBoxResponse>('/api/pocket/grid', data)

/* ---- Batch ---- */
export const batchGenerate = (data: BatchRequest, signal?: AbortSignal) =>
  post<BatchResponse>('/api/batch/generate', data, signal)

/* ---- Minimization ---- */
export const minimize = (data: MinimizeRequest, signal?: AbortSignal) =>
  post<MinimizeResponse>('/api/minimize/', data, signal)

/* ---- Convert ---- */
export const convert = (data: ConvertRequest, signal?: AbortSignal) =>
  post<ConvertResponse>('/api/convert/', data, signal)

/* ---- Pipeline ---- */
export const runPipeline = (data: PipelineRequest, signal?: AbortSignal) =>
  post<PipelineResponse>('/api/pipeline/run', data, signal)

/* ---- Similarity ---- */
export const searchSimilarity = (data: SimilarityRequest) =>
  post<SimilarityResponse>('/api/similarity/search', data)

/* ---- Docking ---- */
export const runDocking = (data: DockingRequest, signal?: AbortSignal) =>
  post<DockingResponse>('/api/docking/run', data, signal)

export const autoGrid = (data: AutoGridRequest) =>
  post<GridBox>('/api/docking/auto-grid', data)

/* ---- Oracle AI ---- */
export const predictOracle = (data: OracleRequest, signal?: AbortSignal) =>
  post<OracleResponse>('/api/oracle/predict', data, signal)

/* ---- Results ---- */
export const loadResults = (dir: string) =>
  get<LoadResultsResponse>(`/api/results/load?dir=${encodeURIComponent(dir)}`)

export const exportTop = (data: ExportTopRequest) =>
  post<{
    exported: number
    output_dir: string
    top_hits_dir: string
    originals_dir: string
    originals_exported?: number
    logs_exported?: number
    total?: number
    missing?: string[]
  }>('/api/results/export-top', data)

export const generateCSVReport = (data: CSVReportRequest) =>
  post<CSVReportResponse>('/api/results/csv-report', data)

/* ---- Compound Filters ---- */
export const scanFilters = (data: FilterRequest) =>
  post<FilterResponse>('/api/filters/scan', data)

/* ---- Extended ADMET ---- */
export const profileADMET = (data: ADMETRequest) =>
  post<ADMETResponse>('/api/admet/profile', data)

export const batchADMET = (smilesList: string[]) =>
  post<ADMETResponse>('/api/admet/batch', { smiles_list: smilesList })

/* ---- Interaction Profiler ---- */
export const analyzeInteractions = (data: InteractionRequest) =>
  post<InteractionResponse>('/api/interactions/analyze', data)

export const getInteractionNetwork = (data: InteractionRequest) =>
  post<{ nodes: { id: string; label: string; type: string }[]; edges: { source: string; target: string; type: string; strength: number; label: string }[]; total_interactions: number }>('/api/interactions/network', data)

/* ---- Chemical Clustering ---- */
export const clusterCompounds = (data: ClusterRequest) =>
  post<ClusterResponse>('/api/cluster/analyze', data)

/* ---- Analog Generator ---- */
export const generateAnalogs = (data: AnalogRequest) =>
  post<AnalogResponse>('/api/analogs/generate', data)

/* ---- Consensus Scoring ---- */
export const consensusScore = (data: ConsensusRequest) =>
  post<ConsensusResponse>('/api/results/consensus', data)

/* ---- IUPAC Resolution ---- */
export const resolveIUPAC = (smiles: string) =>
  get<IUPACResponse>(`/api/results/iupac?smiles=${encodeURIComponent(smiles)}`)

/* ---- Druggability ---- */
export const assessDruggability = (data: DruggabilityRequest) =>
  post<DruggabilityResponse>('/api/pocket/druggability', data)

/* ---- Pose Decomposition ---- */
export const decomposePose = (data: PoseDecompRequest) =>
  post<PoseDecompResponse>('/api/docking/decompose', data)

/* ---- Project Management ---- */
export const listProjects = () =>
  get<{ projects: Project[]; count: number }>('/api/projects/list')

export const saveProject = (data: Project) =>
  post<{ status: string; id: string }>('/api/projects/save', data)

export const loadProject = (id: string) =>
  get<Project>(`/api/projects/load/${id}`)

export const deleteProject = (id: string) =>
  fetch(`${BASE_URL}/api/projects/delete/${id}`, { method: 'DELETE' })
    .then(r => r.json())

/* ---- Compound Watchlist ---- */
export const listWatchlist = () =>
  get<{ items: WatchlistItem[]; count: number }>('/api/watchlist/list')

export const addToWatchlist = (data: WatchlistItem) =>
  post<{ status: string; id: string }>('/api/watchlist/add', data)

export const removeFromWatchlist = (id: string) =>
  fetch(`${BASE_URL}/api/watchlist/remove/${id}`, { method: 'DELETE' })
    .then(r => r.json())

export const updateWatchlistItem = (data: WatchlistItem) =>
  fetch(`${BASE_URL}/api/watchlist/update`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json())

/* ---- Batch Pipeline ---- */
export const runBatchPipeline = (data: BatchPipelineRequest, signal?: AbortSignal) =>
  post<BatchPipelineResponse>('/api/pipeline/batch', data, signal)


/* ---- Molecule Resolver ---- */
export const resolveMolecule = (data: ResolveRequest) =>
  post<ResolveResponse>('/api/resolve/molecule', data)

export const resolveBatch = (inputs: string[]) =>
  post<{ results: ResolveResponse[]; resolved: number; failed: number; total: number }>('/api/resolve/batch', { inputs })

/* ---- Receptor Preparation ---- */
export const analyzePDB = (pdb_path: string, pdb_id?: string) =>
  post<PDBAnalysis>('/api/prepare/analyze', { pdb_path, pdb_id })

export const prepareReceptor = (data: PrepareReceptorRequest) =>
  post<PrepareReceptorResponse>('/api/prepare/run', data)

/* ---- Compound Comparison ---- */
export const compareCompounds = (data: CompareRequest) =>
  post<CompareResponse>('/api/compare/compare', data)

/* ---- Pharmacophore ---- */
export const generatePharmacophore = (data: PharmGenerateRequest) =>
  post<PharmGenerateResponse>('/api/pharmacophore/generate', data)

export const screenPharmacophore = (data: PharmScreenRequest) =>
  post<PharmScreenResponse>('/api/pharmacophore/screen', data)

export const savePharmacophore = (data: PharmSaveRequest) =>
  post<PharmSaveResponse>('/api/pharmacophore/save', data)

export const loadPharmacophore = (path: string) =>
  get<PharmLoadResponse>(`/api/pharmacophore/load?path=${encodeURIComponent(path)}`)

/* ---- Report Generation ---- */
export const generateReport = (data: ReportRequest) =>
  post<ReportResponse>('/api/report/generate', data)

/* ---- Fragment-Based Drug Design ---- */
export const decomposeFragment = (data: FragmentDecomposeRequest) =>
  post<FragmentDecomposeResponse>('/api/fragments/decompose', data)

export const linkFragments = (data: FragmentLinkRequest) =>
  post<FragmentLinkResponse>('/api/fragments/link', data)

export const growFragment = (data: FragmentGrowRequest) =>
  post<FragmentGrowResponse>('/api/fragments/grow', data)

export const getFragmentLibrary = (category?: string) =>
  get<FragmentLibraryResponse>(`/api/fragments/library${category ? `?category=${encodeURIComponent(category)}` : ''}`)

/* ---- Multi-Target Docking ---- */
export const multiTargetDock = (data: MultiTargetRequest) =>
  post<MultiTargetResponse>('/api/docking/multi-target', data)

/* ---- Scaffold Hopping ---- */
export const scaffoldHop = (data: ScaffoldHopRequest) =>
  post<ScaffoldHopResponse>('/api/scaffold/hop', data)
