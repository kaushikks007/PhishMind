export interface ScanHistoryItem {
  id: string;
  sender: string;
  subject: string;
  verdict: 'SAFE' | 'SUSPICIOUS' | 'PHISHING';
  timestamp: string;
}

export interface ScanBreakdown {
  technical: number;
  intent: number;
  social_engineering: number;
  urls: number;
  semantic_support: number;
}

export interface SocialEngineeringFinding {
  technique: string;
  evidence: string;
  severity: 'low' | 'medium' | 'high';
}

// Matches the backend's PhishMind API response `data` shape exactly
// (see backend/main.py -> POST /api/v1/scan and GET /api/v1/scan/{id}).
export interface ScanResult {
  id: string;
  sender: string;
  subject: string;
  body: string;
  verdict: 'SAFE' | 'SUSPICIOUS' | 'PHISHING';
  risk_score: number;
  is_brand_verified: boolean;
  is_brand_verifiable?: boolean;
  claimed_brand?: string | null;
  social_engineering: SocialEngineeringFinding[];
  suspicious_evidence: string[];
  actionable_advice: string[];
  breakdown: ScanBreakdown;
  explanation: string;
  detected_language?: string;
  translated_subject?: string | null;
  translated_body?: string | null;
}
