-- DRISHTI database schema.
-- Three provenance tiers (mirrored by colors in the Excel review workbook):
--   BLUE  : KSP FIR schema exactly as the official ER diagram defines it
--   TEAL  : tables the ER diagram references but never defines (gap-fill)
--   AMBER : DRISHTI intelligence extensions (x_ prefix)

-- ===================================================================== BLUE ==

CREATE TABLE State (
    StateID        INTEGER PRIMARY KEY,
    StateName      TEXT NOT NULL,
    NationalityID  INTEGER,
    Active         INTEGER DEFAULT 1
);

CREATE TABLE District (
    DistrictID   INTEGER PRIMARY KEY,
    DistrictName TEXT NOT NULL,
    StateID      INTEGER REFERENCES State(StateID),
    Active       INTEGER DEFAULT 1
);

CREATE TABLE UnitType (
    UnitTypeID   INTEGER PRIMARY KEY,
    UnitTypeName TEXT NOT NULL,
    CityDistState TEXT,
    Hierarchy    INTEGER,
    Active       INTEGER DEFAULT 1
);

CREATE TABLE Unit (
    UnitID       INTEGER PRIMARY KEY,
    UnitName     TEXT NOT NULL,
    TypeID       INTEGER REFERENCES UnitType(UnitTypeID),
    ParentUnit   INTEGER,
    NationalityID INTEGER,
    StateID      INTEGER REFERENCES State(StateID),
    DistrictID   INTEGER REFERENCES District(DistrictID),
    Active       INTEGER DEFAULT 1
);

CREATE TABLE Rank (
    RankID    INTEGER PRIMARY KEY,
    RankName  TEXT NOT NULL,
    Hierarchy INTEGER,
    Active    INTEGER DEFAULT 1
);

CREATE TABLE Designation (
    DesignationID   INTEGER PRIMARY KEY,
    DesignationName TEXT NOT NULL,
    Active          INTEGER DEFAULT 1,
    SortOrder       INTEGER
);

CREATE TABLE Employee (
    EmployeeID   INTEGER PRIMARY KEY,
    DistrictID   INTEGER REFERENCES District(DistrictID),
    UnitID       INTEGER REFERENCES Unit(UnitID),
    RankID       INTEGER REFERENCES Rank(RankID),
    DesignationID INTEGER REFERENCES Designation(DesignationID),
    KGID         TEXT,
    FirstName    TEXT,
    EmployeeDOB  TEXT,
    GenderID     INTEGER,
    BloodGroupID INTEGER,
    PhysicallyChallenged INTEGER DEFAULT 0,
    AppointmentDate TEXT
);

CREATE TABLE Court (
    CourtID    INTEGER PRIMARY KEY,
    CourtName  TEXT NOT NULL,
    DistrictID INTEGER REFERENCES District(DistrictID),
    StateID    INTEGER REFERENCES State(StateID),
    Active     INTEGER DEFAULT 1
);

CREATE TABLE CaseCategory (
    CaseCategoryID INTEGER PRIMARY KEY,   -- doubles as the CrimeNo leading digit
    LookupValue    TEXT NOT NULL
);

CREATE TABLE GravityOffence (
    GravityOffenceID INTEGER PRIMARY KEY,
    LookupValue      TEXT NOT NULL
);

CREATE TABLE CaseStatusMaster (
    CaseStatusID   INTEGER PRIMARY KEY,
    CaseStatusName TEXT NOT NULL
);

CREATE TABLE CasteMaster (
    caste_master_id   INTEGER PRIMARY KEY,
    caste_master_name TEXT NOT NULL
);

CREATE TABLE ReligionMaster (
    ReligionID   INTEGER PRIMARY KEY,
    ReligionName TEXT NOT NULL
);

CREATE TABLE OccupationMaster (
    OccupationID   INTEGER PRIMARY KEY,
    OccupationName TEXT NOT NULL
);

CREATE TABLE CrimeHead (
    CrimeHeadID    INTEGER PRIMARY KEY,
    CrimeGroupName TEXT NOT NULL,
    Active         INTEGER DEFAULT 1
);

CREATE TABLE CrimeSubHead (
    CrimeSubHeadID INTEGER PRIMARY KEY,
    CrimeHeadID    INTEGER REFERENCES CrimeHead(CrimeHeadID),
    CrimeHeadName  TEXT NOT NULL,          -- (sic) sub-head display name, per ER PDF
    SeqID          INTEGER
);

CREATE TABLE Act (
    ActCode        TEXT PRIMARY KEY,
    ActDescription TEXT,
    ShortName      TEXT,
    Active         INTEGER DEFAULT 1
);

CREATE TABLE Section (
    ActCode            TEXT REFERENCES Act(ActCode),
    SectionCode        TEXT,
    SectionDescription TEXT,
    Active             INTEGER DEFAULT 1,
    PRIMARY KEY (ActCode, SectionCode)
);

CREATE TABLE CrimeHeadActSection (
    CrimeHeadID INTEGER REFERENCES CrimeHead(CrimeHeadID),
    ActCode     TEXT,
    SectionCode TEXT
);

CREATE TABLE CaseMaster (
    CaseMasterID       INTEGER PRIMARY KEY,
    CrimeNo            TEXT NOT NULL,
    CaseNo             TEXT NOT NULL,
    CrimeRegisteredDate TEXT,
    PolicePersonID     INTEGER REFERENCES Employee(EmployeeID),
    PoliceStationID    INTEGER REFERENCES Unit(UnitID),
    CaseCategoryID     INTEGER REFERENCES CaseCategory(CaseCategoryID),
    GravityOffenceID   INTEGER REFERENCES GravityOffence(GravityOffenceID),
    CrimeMajorHeadID   INTEGER REFERENCES CrimeHead(CrimeHeadID),
    CrimeMinorHeadID   INTEGER REFERENCES CrimeSubHead(CrimeSubHeadID),
    CaseStatusID       INTEGER REFERENCES CaseStatusMaster(CaseStatusID),
    CourtID            INTEGER REFERENCES Court(CourtID),
    IncidentFromDate   TEXT,
    IncidentToDate     TEXT,
    InfoReceivedPSDate TEXT,
    latitude           REAL,
    longitude          REAL,
    BriefFacts         TEXT
);

CREATE TABLE ComplainantDetails (
    ComplainantID   INTEGER PRIMARY KEY,
    CaseMasterID    INTEGER REFERENCES CaseMaster(CaseMasterID),
    ComplainantName TEXT,
    AgeYear         INTEGER,
    OccupationID    INTEGER REFERENCES OccupationMaster(OccupationID),
    ReligionID      INTEGER REFERENCES ReligionMaster(ReligionID),
    CasteID         INTEGER REFERENCES CasteMaster(caste_master_id),
    GenderID        INTEGER
);

CREATE TABLE Victim (
    VictimMasterID INTEGER PRIMARY KEY,
    CaseMasterID   INTEGER REFERENCES CaseMaster(CaseMasterID),
    VictimName     TEXT,
    AgeYear        INTEGER,
    GenderID       TEXT,      -- source schema stores lookup-ish free text (m/f/t)
    VictimPolice   TEXT       -- source schema quirk: '1'/'0' in VARCHAR
);

CREATE TABLE Accused (
    AccusedMasterID INTEGER PRIMARY KEY,
    CaseMasterID    INTEGER REFERENCES CaseMaster(CaseMasterID),
    AccusedName     TEXT,
    AgeYear         INTEGER,
    GenderID        TEXT,     -- M/F/T per ER PDF
    PersonID        TEXT      -- NOT an identity: A1/A2/A3 ordering within the case
);

CREATE TABLE ActSectionAssociation (
    CaseMasterID  INTEGER REFERENCES CaseMaster(CaseMasterID),
    ActID         TEXT,
    SectionID     TEXT,
    ActOrderID    INTEGER,
    SectionOrderID INTEGER
);

CREATE TABLE ArrestSurrender (
    ArrestSurrenderID     INTEGER PRIMARY KEY,
    CaseMasterID          INTEGER REFERENCES CaseMaster(CaseMasterID),
    ArrestSurrenderTypeID INTEGER,
    ArrestSurrenderDate   TEXT,
    ArrestSurrenderStateId INTEGER REFERENCES State(StateID),
    ArrestSurrenderDistrictId INTEGER REFERENCES District(DistrictID),
    PoliceStationID       INTEGER REFERENCES Unit(UnitID),
    IOID                  INTEGER REFERENCES Employee(EmployeeID),
    CourtID               INTEGER REFERENCES Court(CourtID),
    AccusedMasterID       INTEGER REFERENCES Accused(AccusedMasterID),
    IsAccused             INTEGER DEFAULT 1,
    IsComplainantAccused  INTEGER DEFAULT 0
);

CREATE TABLE inv_arrestsurrenderaccused (
    ArrestSurrenderID INTEGER REFERENCES ArrestSurrender(ArrestSurrenderID),
    AccusedMasterID   INTEGER REFERENCES Accused(AccusedMasterID)
);

CREATE TABLE ChargesheetDetails (
    CSID          INTEGER PRIMARY KEY,
    CaseMasterID  INTEGER REFERENCES CaseMaster(CaseMasterID),
    csdate        TEXT,
    cstype        TEXT,      -- A=Chargesheet, B=False Case, C=Undetected
    PolicePersonID INTEGER REFERENCES Employee(EmployeeID)
);

-- ===================================================================== TEAL ==
-- Referenced by the ER diagram but never defined there; we complete the schema.

CREATE TABLE GenderMaster (
    GenderID   INTEGER PRIMARY KEY,
    GenderCode TEXT NOT NULL,
    GenderName TEXT NOT NULL
);

CREATE TABLE ArrestSurrenderTypeMaster (
    ArrestSurrenderTypeID INTEGER PRIMARY KEY,
    LookupValue           TEXT NOT NULL
);

CREATE TABLE BloodGroupMaster (
    BloodGroupID INTEGER PRIMARY KEY,
    LookupValue  TEXT NOT NULL
);

CREATE TABLE PlaceTypeMaster (
    PlaceTypeID INTEGER PRIMARY KEY,
    LookupValue TEXT NOT NULL
);

CREATE TABLE Inv_OccuranceTime (
    CaseMasterID       INTEGER PRIMARY KEY REFERENCES CaseMaster(CaseMasterID),
    OccurrenceHourBand TEXT,     -- e.g. '05-08', '23-04'
    PlaceTypeID        INTEGER REFERENCES PlaceTypeMaster(PlaceTypeID),
    POIName            TEXT
);

-- ==================================================================== AMBER ==
-- DRISHTI intelligence extensions. The KSP schema stores records; these tables
-- turn records into intelligence. All engine-written rows carry provenance.

CREATE TABLE x_unit_geo (
    UnitID    INTEGER PRIMARY KEY REFERENCES Unit(UnitID),
    latitude  REAL,
    longitude REAL
);

CREATE TABLE x_person_master (
    person_id        INTEGER PRIMARY KEY,
    canonical_name   TEXT NOT NULL,
    gender           TEXT,
    birth_year_est   INTEGER,
    home_district_id INTEGER REFERENCES District(DistrictID),
    religion         TEXT,
    aadhaar          TEXT,     -- synthetic 12-digit (never starts 0/1); world truth
    phone            TEXT,     -- synthetic mobile; world truth
    risk_score       REAL,
    first_seen       TEXT,
    last_seen        TEXT
);

-- IDs the police ACTUALLY captured in a case record (partial and messy on
-- purpose: complainants ~55%, victims ~45%, arrested accused ~40%, ~2% typos).
-- ER uses these as high-confidence links when present; names/age/geo otherwise.
CREATE TABLE x_identity_capture (
    CaseMasterID  INTEGER REFERENCES CaseMaster(CaseMasterID),
    role          TEXT,          -- accused | victim | complainant
    source_row_id INTEGER,
    id_type       TEXT,          -- aadhaar | phone
    id_value      TEXT,          -- full synthetic value (data is synthetic;
                                 -- production would display masked)
    id_hash       TEXT,          -- salted hash of the FULL entered value; lets
                                 -- ER hard-link without storing the number
    captured_on   TEXT
);

CREATE TABLE x_district_indicators (
    district_id  INTEGER PRIMARY KEY REFERENCES District(DistrictID),
    pop_2011     INTEGER,
    pop_estimate INTEGER,
    urban_pct    REAL,
    literacy_pct REAL,
    sex_ratio    INTEGER
);

CREATE TABLE x_property (
    property_id  INTEGER PRIMARY KEY,
    CaseMasterID INTEGER REFERENCES CaseMaster(CaseMasterID),
    kind         TEXT,           -- vehicle | gold-jewellery | cash | mobile | other
    description  TEXT,
    identifier   TEXT,           -- vehicle reg no / IMEI when applicable
    value_inr    REAL,
    recovered    INTEGER DEFAULT 0
);

CREATE TABLE x_person_case_role (
    person_id     INTEGER REFERENCES x_person_master(person_id),
    CaseMasterID  INTEGER REFERENCES CaseMaster(CaseMasterID),
    role          TEXT,          -- accused | victim | complainant
    source_row_id INTEGER,       -- PK in the corresponding source table
    match_score   REAL,          -- ER confidence; 1.0 for generator-linked rows
    match_basis   TEXT           -- explainability: what the merge relied on
);

CREATE TABLE x_person_alias (
    person_id INTEGER REFERENCES x_person_master(person_id),
    alias     TEXT NOT NULL,
    kind      TEXT               -- spelling-variant | true-alias
);

CREATE TABLE x_er_gold (
    source_table  TEXT,
    source_row_id INTEGER,
    true_person_id INTEGER REFERENCES x_person_master(person_id)
);

CREATE TABLE x_mo_tag (
    CaseMasterID INTEGER REFERENCES CaseMaster(CaseMasterID),
    tag          TEXT NOT NULL,
    source       TEXT,           -- rule | glm
    confidence   REAL
);

CREATE TABLE x_fin_account (
    account_id  INTEGER PRIMARY KEY,
    kind        TEXT,             -- bank | upi | wallet
    institution TEXT,
    holder_person_id INTEGER REFERENCES x_person_master(person_id)
);

CREATE TABLE x_fin_txn (
    txn_id       INTEGER PRIMARY KEY,
    from_account INTEGER REFERENCES x_fin_account(account_id),
    to_account   INTEGER REFERENCES x_fin_account(account_id),
    amount       REAL,
    ts           TEXT,
    channel      TEXT,            -- imps | upi | neft | cash-deposit
    CaseMasterID INTEGER          -- nullable link to a registered case
);

CREATE TABLE x_network_edge (
    src_type TEXT, src_id INTEGER,
    dst_type TEXT, dst_id INTEGER,
    edge_type TEXT,               -- co-accused | shared-location | shared-account | arrested-together
    weight    REAL,
    evidence  TEXT                -- JSON list of CaseMasterIDs
);

CREATE TABLE x_agg_daily (
    unit_id       INTEGER REFERENCES Unit(UnitID),
    district_id   INTEGER REFERENCES District(DistrictID),
    crime_head_id INTEGER REFERENCES CrimeHead(CrimeHeadID),
    date          TEXT,
    n             INTEGER,
    PRIMARY KEY (unit_id, crime_head_id, date)
);

CREATE TABLE x_alert (
    alert_id   INTEGER PRIMARY KEY,
    kind       TEXT,               -- spike | anomaly | emerging-trend
    scope_type TEXT, scope_id INTEGER,
    crime_head_id INTEGER,
    window_start TEXT, window_end TEXT,
    observed   REAL, baseline REAL, zscore REAL,
    summary    TEXT,
    evidence   TEXT                -- JSON list of CaseMasterIDs
);

CREATE TABLE x_role (
    role_id   INTEGER PRIMARY KEY,
    role_name TEXT,               -- DGP | RANGE_DIG | DISTRICT_SP | STATION_IO | SCRB_ANALYST
    scope_type TEXT               -- state | range | district | station
);

CREATE TABLE x_app_user (
    user_id   INTEGER PRIMARY KEY,
    username  TEXT UNIQUE,
    pass_hash TEXT,
    role_id   INTEGER REFERENCES x_role(role_id),
    scope_id  INTEGER              -- unit/district id matching the role's scope_type
);

CREATE TABLE x_audit_log (
    log_id  INTEGER PRIMARY KEY,
    user_id INTEGER,
    ts      TEXT,
    action  TEXT,
    detail  TEXT
);

CREATE TABLE x_provenance (
    table_name TEXT,
    column_name TEXT,
    provenance TEXT               -- real-reference | synthetic | gap-fill
);

-- ================================================================== INDEXES ==

CREATE INDEX idx_case_regdate  ON CaseMaster(CrimeRegisteredDate);
CREATE INDEX idx_case_station  ON CaseMaster(PoliceStationID);
CREATE INDEX idx_case_head     ON CaseMaster(CrimeMajorHeadID);
CREATE INDEX idx_case_geo      ON CaseMaster(latitude, longitude);
CREATE INDEX idx_accused_case  ON Accused(CaseMasterID);
CREATE INDEX idx_victim_case   ON Victim(CaseMasterID);
CREATE INDEX idx_compl_case    ON ComplainantDetails(CaseMasterID);
CREATE INDEX idx_asa_case      ON ActSectionAssociation(CaseMasterID);
CREATE INDEX idx_arrest_case   ON ArrestSurrender(CaseMasterID);
CREATE INDEX idx_cs_case       ON ChargesheetDetails(CaseMasterID);
CREATE INDEX idx_pcr_person    ON x_person_case_role(person_id);
CREATE INDEX idx_pcr_case      ON x_person_case_role(CaseMasterID);
CREATE INDEX idx_edge_src      ON x_network_edge(src_type, src_id);
CREATE INDEX idx_edge_dst      ON x_network_edge(dst_type, dst_id);
CREATE INDEX idx_occtime_case ON Inv_OccuranceTime(CaseMasterID);
CREATE INDEX idx_property_case ON x_property(CaseMasterID);
CREATE INDEX idx_agg_unit_date ON x_agg_daily(unit_id, date);
CREATE INDEX idx_agg_district  ON x_agg_daily(district_id, date);
CREATE INDEX idx_txn_from      ON x_fin_txn(from_account);
CREATE INDEX idx_txn_to        ON x_fin_txn(to_account);
CREATE INDEX idx_idcap_case    ON x_identity_capture(CaseMasterID);
CREATE INDEX idx_idcap_source  ON x_identity_capture(role, source_row_id);
CREATE INDEX idx_gold_source   ON x_er_gold(source_row_id);
CREATE INDEX idx_gold_person   ON x_er_gold(true_person_id);
CREATE INDEX idx_idcap_value   ON x_identity_capture(id_type, id_value);
CREATE INDEX idx_property_ident ON x_property(identifier);
CREATE INDEX idx_unit_district ON Unit(DistrictID);
CREATE INDEX idx_emp_unit      ON Employee(UnitID);
