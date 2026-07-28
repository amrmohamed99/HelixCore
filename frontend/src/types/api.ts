/* ================================================================
   TypeScript interfaces mirroring backend Pydantic schemas
   ================================================================ */

/* ---- Health ---- */
export interface HealthResponse {
  status: string
  message: string
}

/* ---- Global Job Progress ---- */
export type JobStatus = 'running' | 'paused' | 'terminating' | 'cancelled' | 'completed' | 'error'

export interface JobSnapshot {
  id: string
  name: string
  status: JobStatus
  progress: number
  message: string
  current: number
  total: number
  started_at: number
  updated_at: number
}

export interface JobControlResponse {
  success: boolean
  message: string
  job: JobSnapshot | null
}

/* ---- System ---- */
export interface SystemStats {
  cpu_percent: number
  ram_percent: number
  cores: number
  ram_total_gb: number
}

/* ---- PDB Fetch ---- */
export interface FetchPDBRequest {
  pdb_id: string
  output_dir: string
}

export interface FetchPDBResponse {
  pdb_path: string
  message: string
}

/* ---- UniProt ---- */
export interface UniprotInfo {
  accession: string
  entry_name: string
  gene: string
  organism: string
  function: string
  pathways: string[]
  bio_processes: string[]
  chembl_id: string | null
  network_image_url: string | null
}

/* ---- Drug Info ---- */
export interface DrugInfo {
  name: string
  chembl_id: string
  smiles: string | null
  affinity_type: string | null
  affinity_value: string | null
  source: string
}

/* ---- Pocket ---- */
export interface PocketAnalysisRequest {
  pdb_path: string
  ligand_name?: string
  ligand_chain?: string
  ligand_resseq?: number
  ligand_icode?: string
  padding?: number
}

export interface Residue {
  name: string
  seq: string
}

export interface PocketAnalysisResponse {
  residues: string[]
  ligand_atom_count: number
  contact_count: number
  selected_ligand?: Record<string, string | number | null>
}

export interface GridBox {
  center_x: number
  center_y: number
  center_z: number
  size_x: number
  size_y: number
  size_z: number
}

export interface GridBoxResponse {
  grid: GridBox
  output_path: string | null
  ligand_atom_count: number
  selected_ligand?: Record<string, string | number | null>
}

/* ---- Batch ---- */
export interface BatchRequest {
  smiles_file: string
}

export interface ProcessingFailure {
  item: string
  reason: string
  detail?: string | null
}

export interface BatchResponse {
  output_dir: string
  generated: number
  failed: number
  failures: ProcessingFailure[]
}

/* ---- Minimization ---- */
export interface MinimizeRequest {
  directory: string
  force_field?: string
}

export interface MinimizeResponse {
  output_dir: string
  processed: number
  failed: number
  failures: ProcessingFailure[]
}

/* ---- Convert ---- */
export interface ConvertRequest {
  directory: string
}

export interface ConvertResponse {
  output_dir: string
  converted: number
  failed?: number
  failures: ProcessingFailure[]
}

/* ---- Pipeline ---- */
export interface PipelineRequest {
  smiles: string
  name?: string
  receptor: string
  config: string
}

export interface PipelineResponse {
  score: string | null
  output_path: string | null
  message: string
}

/* ---- Similarity ---- */
export interface SimilarityRequest {
  query: string
  method?: string
  database?: string
  local_db_path?: string | null
}

export interface SimilarityHit {
  name: string
  score: string
  smiles: string | null
}

export interface SimilarityResponse {
  hits: SimilarityHit[]
  report_path: string | null
}

/* ---- Docking ---- */
export interface DockingRequest {
  ligands_dir: string
  receptor: string
  config_path?: string | null
  grid?: GridBox | null
  exhaustiveness?: number
  seed?: number
}

export interface DockingResult {
  ligand: string
  score: number | null
  output_path: string | null
  status: string
  error_detail: string | null
}

export interface DockingResponse {
  results: DockingResult[]
  results_dir: string | null
}

export interface AutoGridRequest {
  receptor_path: string
  padding?: number
}

/* ---- Oracle AI ---- */
export interface OracleRequest {
  dock_dir: string
  model_path?: string | null
}

export interface OraclePrediction {
  ligand: string
  vina_score: number
  predicted_pKd: number
  confidence: string
  method: string
}

export interface OracleResponse {
  predictions: OraclePrediction[]
  csv_path: string | null
}

/* ---- Results ---- */
export interface Candidate {
  name: string
  score: number
  dir: string
}

export interface LoadResultsResponse {
  candidates: Candidate[]
}

export interface ExportTopRequest {
  top_n?: number
  src_dir: string
  results_dir: string
}

export interface CSVReportRequest {
  res_dir: string
  src_dir?: string
  top_n?: number
  ro5?: Ro5Thresholds
}

export interface CSVRow {
  rank: number
  ligand: string
  score: number
  mw: number | null
  logp: number | null
  hbd: number | null
  hba: number | null
  tpsa: number | null
  rule_of_5: string
}

export interface CSVReportResponse {
  rows: CSVRow[]
  csv_path: string | null
}

/* ---- Compound Filters (PAINS + Structural Alerts) ---- */
export interface FilterRequest {
  input_path: string
  covalent_mode?: boolean
}

export interface FilteredCompound {
  name: string
  smiles: string
  pains_free: boolean
  pains_matches: string[]
  alert_free: boolean
  alerts: string[]
  passed: boolean
}

export interface FilterResponse {
  compounds: FilteredCompound[]
  total: number
  passed: number
  flagged: number
  report_path: string | null
}

/* ---- Extended ADMET ---- */
export interface Ro5Thresholds {
  mw?: number
  logp?: number
  hbd?: number
  hba?: number
  max_violations?: number
}

export interface ADMETRequest {
  smiles?: string | null
  file_path?: string | null
  ro5?: Ro5Thresholds
}

/** One threshold of the BBB triage filter and the descriptor it was applied to. */
export interface BBBTriageCriterion {
  /** Descriptor name, e.g. "MW", "TPSA", "LogP" */
  name: string
  /** The computed descriptor value */
  value: number | null
  /** Comparison applied, e.g. "<" or "within" */
  operator: string
  /** Human-readable bound, e.g. "450" or "[0.5, 4.5]" */
  threshold: string
  passed: boolean
}

/**
 * BBB triage flag — a three-threshold descriptor filter, NOT a trained
 * blood-brain-barrier permeability model. The thresholds that produced the
 * verdict are returned so the user can see the basis for it.
 */
export interface BBBTriage {
  flag: boolean
  criteria: BBBTriageCriterion[]
  caveat: string
}

export interface ADMETProfile {
  name: string
  smiles: string
  mw: number
  logp: number
  hbd: number
  hba: number
  tpsa: number
  rotatable_bonds: number
  qed: number | null
  sa_score: number | null
  bertz_ct: number | null
  esol_logS: number | null
  /** Verdict of the three-threshold BBB triage filter. Not a trained model. */
  bbb_triage_flag: boolean | null
  /** The thresholds, descriptor values and per-rule verdicts behind the flag. */
  bbb_triage: BBBTriage | null
  /** @deprecated Alias of `bbb_triage_flag`, kept for backward compatibility. */
  bbb_permeable: boolean | null
  rule_of_5: string
  ro5_violations: number
}

export interface ADMETResponse {
  profiles: ADMETProfile[]
  csv_path: string | null
}

/* ---- Interaction Profiler ---- */
export interface InteractionRequest {
  receptor_path: string
  ligand_path: string
  cutoff?: number
}

/**
 * A single interaction *label* on one receptor-atom/ligand-atom pair.
 * Classification is multi-label: a charge-complementary pair that also sits
 * inside the hydrogen-bond distance produces two entries sharing the same
 * `residue`/`receptor_atom`/`ligand_atom` with different `type`.
 */
export interface Interaction {
  type: string
  residue: string
  distance: number
  ligand_atom: string | null
  receptor_atom: string | null
}

export interface InteractionResponse {
  interactions: Interaction[]
  h_bonds: number
  hydrophobic: number
  /** Exhaustive: includes charge-complementary pairs that are also H-bonded. */
  salt_bridges: number
  /** Legacy count: salt bridges on pairs not already labelled as hydrogen bonds. */
  salt_bridges_single_label: number
  /** Label assignments — equals `interactions.length`. */
  total: number
  /** Distinct atom pairs with at least one label (the pre-multi-label `total`). */
  total_single_label: number
  /** Pairs carrying more than one label (currently only H-bond + salt bridge). */
  dual_labeled_pairs: number
}

/* ---- Chemical Clustering ---- */
export interface ClusterRequest {
  results_dir: string
  src_dir?: string
  method?: string
  cutoff?: number
}

export interface ClusterMember {
  name: string
  score: number
  smiles: string | null
  is_centroid: boolean
}

export interface Cluster {
  cluster_id: number
  size: number
  members: ClusterMember[]
}

export interface ClusterResponse {
  clusters: Cluster[]
  total_compounds: number
  num_clusters: number
  singletons: number
}

/* ---- Analog Generator ---- */
export interface AnalogRequest {
  smiles: string
  name?: string
  method?: string
  max_analogs?: number
}

export interface AnalogCompound {
  name: string
  smiles: string
  similarity: number | null
  mw: number | null
}

export interface AnalogResponse {
  parent_smiles: string
  analogs: AnalogCompound[]
  count: number
}

/* ---- Consensus Scoring ---- */
export interface ConsensusRequest {
  results_dir: string
  src_dir?: string
}

export interface ConsensusResult {
  ligand: string
  vina_score: number | null
  vina_rank: number | null
  mmff_energy: number | null
  energy_rank: number | null
  contact_score: number | null
  contact_rank: number | null
  consensus_rank: number | null
}

export interface ConsensusResponse {
  results: ConsensusResult[]
  csv_path: string | null
}

/* ---- Druggability Assessment ---- */
export interface DruggabilityRequest {
  pdb_path: string
  ligand_name?: string
  ligand_chain?: string
  ligand_resseq?: number
  ligand_icode?: string
}

export interface DruggabilityResponse {
  volume: number | null
  hydrophobicity_ratio: number | null
  residue_count: number
  druggable: boolean
  confidence: string
  notes: string[]
}

/* ---- Pose Energy Decomposition ---- */
export interface PoseDecompRequest {
  log_path: string
}

export interface EnergyComponent {
  component: string
  value: number
}

export interface PoseDecompResponse {
  ligand: string
  total_score: number | null
  components: EnergyComponent[]
}

/* ---- Project Management ---- */
export interface Project {
  id: string
  name: string
  target_name?: string
  pdb_id?: string
  receptor_path?: string
  grid_config?: string
  ligand_source?: string
  notes?: string
  created?: string
  updated?: string
  pipeline_state?: Record<string, unknown>
  page_inputs?: Record<string, unknown>
  session_data?: Record<string, unknown>
}

/* ---- Compound Watchlist ---- */
export interface WatchlistItem {
  id: string
  name: string
  smiles?: string | null
  score?: number | null
  source?: string
  notes?: string
  added?: string
}

/* ---- Batch Pipeline ---- */
export interface BatchPipelineRequest {
  smiles_file: string
  receptor: string
  config: string
  force_field?: string
  run_filters?: boolean
  run_admet?: boolean
}

export interface BatchPipelineStep {
  step: string
  status: string
  count: number
  message?: string
}

export interface BatchPipelineResponse {
  steps: BatchPipelineStep[]
  results_dir: string | null
  total_docked: number
  failed_docked: number
  best_score: number | null
  message: string
}

/* ---- IUPAC Name Resolution ---- */
export interface IUPACResponse {
  smiles: string
  iupac_name: string | null
  common_name: string | null
}

/* ---- Molecule Resolver ---- */
export interface ResolveRequest {
  input: string
}

export interface ResolveResponse {
  smiles: string
  input_type: string
  name: string | null
}

/* ---- Receptor Preparation ---- */
export interface PrepareReceptorRequest {
  pdb_path: string
  keep_chain?: string
  remove_water?: boolean
  remove_ligands?: boolean
  remove_ions?: boolean
  add_hydrogens?: boolean
}

export interface PrepareReceptorResponse {
  output_path: string
  clean_pdb_path: string
  removed_waters: number
  removed_ligands: number
  removed_ions: number
  message: string
  integrity?: ProteinIntegrityComparison | null
  prep_engine?: string
  warnings?: string[]
}

export interface PDBAnalysis {
  pdb_path: string
  chains: string[]
  ligands: string[]
  water_count: number
  ions: string[]
  atom_count: number
  integrity?: ProteinIntegrityReport
}

export interface ProteinIntegrityReport {
  status: 'ok' | 'warning'
  atom_count: number
  model_count: number
  residue_count: number
  chains: string[]
  chain_residue_counts: Record<string, number>
  sequence_gaps: Array<{ chain: string; from: number; to: number; missing_count: number }>
  ca_breaks: Array<{ chain: string; from: number; to: number; distance: number }>
  missing_backbone: Array<{ chain: string; residue: number; icode: string; resname: string; missing: string[] }>
  warnings: string[]
}

export interface ProteinIntegrityComparison {
  before: ProteinIntegrityReport
  after: ProteinIntegrityReport
  atom_delta: number
  residue_delta: number
  removed_chains: string[]
  status: 'ok' | 'warning'
  warnings: string[]
}

/* ---- Compound Comparison ---- */
export interface CompoundProfile {
  name: string
  smiles: string
  mw: number
  logp: number
  hbd: number
  hba: number
  tpsa: number
  rotatable_bonds: number
  rings: number
  heavy_atoms: number
  qed: number | null
  sa_score: number | null
  rule_of_5: string
  ro5_violations: number
}

export interface CompareRequest {
  smiles_list: string[]
  names?: string[]
  ro5_mw?: number
  ro5_logp?: number
  ro5_hbd?: number
  ro5_hba?: number
  ro5_max_violations?: number
}

export interface CompareResponse {
  compounds: CompoundProfile[]
  property_ranges: Record<string, { min: number; max: number; mean: number }>
}

/* ---- Pharmacophore ---- */
export interface PharmacophoreFeature {
  type: string
  atoms: number[]
  x?: number | null
  y?: number | null
  z?: number | null
  radius: number
}

export interface PharmGenerateRequest {
  smiles: string
  include_3d?: boolean
}

export interface PharmGenerateResponse {
  smiles: string
  features: PharmacophoreFeature[]
  svg?: string | null
  feature_counts: Record<string, number>
  message: string
}

export interface PharmScreenRequest {
  reference_smiles: string
  library_source: string
  mode: '2d' | '3d'
  threshold?: number
}

export interface PharmScreenHit {
  name: string
  smiles: string
  score: number
  matched_features: number
}

export interface PharmScreenResponse {
  hits: PharmScreenHit[]
  total_screened: number
  mode: string
  warning?: string | null
  message: string
}

export interface PharmSaveRequest {
  name: string
  reference_smiles: string
  features: PharmacophoreFeature[]
  output_dir: string
}

export interface PharmSaveResponse {
  path: string
  message: string
}

export interface PharmLoadResponse {
  name: string
  reference_smiles: string
  features: PharmacophoreFeature[]
  path: string
}

/* ---- Report Generation ---- */
export interface ReportSection {
  title: string
  type: 'text' | 'stats' | 'table'
  content: unknown
}

export interface ReportRequest {
  title?: string
  format?: 'pdf' | 'html' | 'both'
  results_dir?: string
  sections?: ReportSection[]
  output_dir?: string
  project_name?: string
  author?: string
  custom_text?: string
}

export interface ReportResponse {
  paths: string[]
  message: string
}

/* ---- Fragment-Based Drug Design ---- */
export interface FragmentDecomposeRequest {
  smiles: string
  method?: 'brics' | 'recap' | 'murcko'
}

export interface FragmentDecomposeResponse {
  smiles: string
  fragments: string[]
  method: string
  count: number
  message: string
}

export interface FragmentLinkRequest {
  fragments: string[]
  max_results?: number
}

export interface FragmentLinkResponse {
  products: string[]
  count: number
  message: string
}

export interface FragmentGrowRequest {
  core: string
  growth_vectors?: number
  max_results?: number
}

export interface FragmentGrowResponse {
  grown: string[]
  count: number
  message: string
}

export interface FragmentLibraryEntry {
  smiles: string
  name: string
  category: string
  mw: number
  rule_of_3: boolean
}

export interface FragmentLibraryResponse {
  fragments: FragmentLibraryEntry[]
  total: number
  categories: string[]
}

/* ---- Scaffold Hopping ---- */
export interface ScaffoldHopRequest {
  smiles: string
  method?: 'murcko' | 'mcs' | 'rgroup' | 'mmp'
  library_path?: string
  max_results?: number
}

export interface ScaffoldHopResult {
  smiles: string
  scaffold: string
  similarity: number
  name: string
}

export interface ScaffoldHopResponse {
  reference: string
  method: string
  reference_scaffold: string
  results: ScaffoldHopResult[]
  count: number
  message: string
}

/* ---- Multi-Target Docking ---- */
export interface MultiTargetRequest {
  ligands_dir: string
  receptors: string[]
  config_paths?: string[]
  grids?: Record<string, unknown>[]
  exhaustiveness?: number
  seed?: number
  mode?: 'sequential' | 'parallel'
}

export interface MultiTargetResult {
  receptor: string
  ligand: string
  score: number | null
  status: string
  output_path: string | null
}

export interface MultiTargetResponse {
  results: MultiTargetResult[]
  selectivity_matrix: Record<string, Record<string, number | null>>
  results_dir: string
  message: string
}
