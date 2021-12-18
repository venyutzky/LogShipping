# CUSTOM LOG SHIPPING USING SQL SERVER

## General Info
Project ini merupakan bagian final project dari mata kuliah teknologi basis data. Inti dari final project ini adalah membuat sebuah custom log shipping. 

Gambaran Arsitektur<br>

![arsitektur TBD](https://user-images.githubusercontent.com/54930670/146624199-4863dce1-b9a0-4b22-92d4-8977bd22b83b.png)
<br>

## Pembuatan Script Backup and Restore di SQL Server
### Alat dan Bahan
  * Windows
  * SQL Server 2019 Express Edition :
    - master instance : VENYUTZKY
    - Backup instance : VENYUTZKY\SEC1
    - Backup instance : VENYUTZKY\SEC2
  * SSMS

### Tahapan Pembuatan
#### 1. Menghubungkan instance backup ke instance master
Tahap ini membuat link dari master ke semua backup instance.<br>
Untuk `VENYUTZKY\SEC1`

```
USE [master];
GO
DECLARE @s NVARCHAR(128) = N'.\SEC1',
        @t NVARCHAR(128) = N'true';
EXEC [master].dbo.sp_addlinkedserver   @server     = @s, @srvproduct = N'SQL Server';
EXEC [master].dbo.sp_addlinkedsrvlogin @rmtsrvname = @s, @useself = @t;
EXEC [master].dbo.sp_serveroption      @server     = @s, @optname = N'collation compatible', @optvalue = @t;
EXEC [master].dbo.sp_serveroption      @server     = @s, @optname = N'data access',          @optvalue = @t;
EXEC [master].dbo.sp_serveroption      @server     = @s, @optname = N'rpc',                  @optvalue = @t;
EXEC [master].dbo.sp_serveroption      @server     = @s, @optname = N'rpc out',              @optvalue = @t;
```
Untuk `VENYUTZKY\SEC2`
```
USE [master];
GO
DECLARE @s NVARCHAR(128) = N'.\SEC2',
        @t NVARCHAR(128) = N'true';
EXEC [master].dbo.sp_addlinkedserver   @server     = @s, @srvproduct = N'SQL Server';
EXEC [master].dbo.sp_addlinkedsrvlogin @rmtsrvname = @s, @useself = @t;
EXEC [master].dbo.sp_serveroption      @server     = @s, @optname = N'collation compatible', @optvalue = @t;
EXEC [master].dbo.sp_serveroption      @server     = @s, @optname = N'data access',          @optvalue = @t;
EXEC [master].dbo.sp_serveroption      @server     = @s, @optname = N'rpc',                  @optvalue = @t;
EXEC [master].dbo.sp_serveroption      @server     = @s, @optname = N'rpc out',              @optvalue = @t;
```

#### 2. Pembuatan Database dan Table
a. Membuat sebuah database pada master instance.
```
USE [master];
CREATE DATABASE TBD;
ALTER DATABASE TBD SET RECOVERY FULL;
```
b. Membuat tabel `PMAG_Databases` di dalam database `TBD`. <br>
tabel ini berfungsi untuk menampung informasi nama database apa yang akan dibackup.
```
USE [TBD];
GO
CREATE TABLE dbo.PMAG_Databases
(
  DatabaseName               SYSNAME,
  LogBackupFrequency_Minutes SMALLINT NOT NULL DEFAULT (15),
  CONSTRAINT PK_DBS PRIMARY KEY(DatabaseName)
);
GO
```
c. Membuat tabel `PMAG_Secondaries` <br>
Tabel ini akan berisi informasi mengenai backup instance yang ada.
```
CREATE TABLE dbo.PMAG_Secondaries
(
  DatabaseName     SYSNAME,
  ServerInstance   SYSNAME,
  CommonFolder     VARCHAR(512) NOT NULL,
  DataFolder       VARCHAR(512) NOT NULL,
  LogFolder        VARCHAR(512) NOT NULL,
  StandByLocation  VARCHAR(512) NOT NULL,
  IsCurrentStandby BIT NOT NULL DEFAULT 0,
  CONSTRAINT PK_Sec PRIMARY KEY(DatabaseName, ServerInstance),
  CONSTRAINT FK_Sec_DBs FOREIGN KEY(DatabaseName)
    REFERENCES dbo.PMAG_Databases(DatabaseName)
);
```
d. Membuat tabel `PMAG_LogBackupHistory`<br>
Tabel ini berisi informasi tentang log backup yang berhasil dilakukan.
```
CREATE TABLE dbo.PMAG_LogBackupHistory
(
  DatabaseName   SYSNAME,
  ServerInstance SYSNAME,
  BackupSetID    INT NOT NULL,
  Location       VARCHAR(2000) NOT NULL,
  BackupTime     DATETIME NOT NULL DEFAULT SYSDATETIME(),
  CONSTRAINT PK_LBH PRIMARY KEY(DatabaseName, ServerInstance, BackupSetID),
  CONSTRAINT FK_LBH_DBs FOREIGN KEY(DatabaseName)
    REFERENCES dbo.PMAG_Databases(DatabaseName),
  CONSTRAINT FK_LBH_Sec FOREIGN KEY(DatabaseName, ServerInstance)
    REFERENCES dbo.PMAG_Secondaries(DatabaseName, ServerInstance)
);
```
e. Membuat tabel `PMAG_LogRestoreHistory` <br>
Tabel ini berisi informasi tentang log restore yang berhasil dilakukan.
```
CREATE TABLE dbo.PMAG_LogRestoreHistory
(
  DatabaseName   SYSNAME,
  ServerInstance SYSNAME,
  BackupSetID    INT,
  RestoreTime    DATETIME,
  CONSTRAINT PK_LRH PRIMARY KEY(DatabaseName, ServerInstance, BackupSetID),
  CONSTRAINT FK_LRH_DBs FOREIGN KEY(DatabaseName)
    REFERENCES dbo.PMAG_Databases(DatabaseName),
  CONSTRAINT FK_LRH_Sec FOREIGN KEY(DatabaseName, ServerInstance)
    REFERENCES dbo.PMAG_Secondaries(DatabaseName, ServerInstance)
);
```
#### 3. Pembuatan Store Procedure<br>
a. Membuat Store Procedure `PMAG_Backup`
Store procedure ini berfungsi untuk menangani proses backup pada database `TBD`
```
CREATE PROCEDURE [dbo].[PMAG_Backup]
  @dbname SYSNAME,
  @type   CHAR(3) = 'bak', -- or 'trn'
  @init   BIT     = 0 -- only used with 'bak'
AS
BEGIN
  SET NOCOUNT ON;
 
  -- generate a filename pattern
  DECLARE @now DATETIME = SYSDATETIME();
  DECLARE @fn NVARCHAR(256) = @dbname + N'_' + CONVERT(CHAR(8), @now, 112) 
    + RIGHT(REPLICATE('0',6) + CONVERT(VARCHAR(32), DATEDIFF(SECOND, 
      CONVERT(DATE, @now), @now)), 6) + N'.' + @type;
 
  -- generate a backup command with MIRROR TO for each distinct CommonFolder
  DECLARE @sql NVARCHAR(MAX) = N'BACKUP' 
    + CASE @type WHEN 'bak' THEN N' DATABASE ' ELSE N' LOG ' END
    + QUOTENAME(@dbname) + ' 
    ' + STUFF(
        (SELECT DISTINCT CHAR(13) + CHAR(10) + N' MIRROR TO DISK = ''' 
           + s.CommonFolder + @fn + ''''
         FROM dbo.PMAG_Secondaries AS s 
         WHERE s.DatabaseName = @dbname 
         FOR XML PATH(''), TYPE).value(N'.[1]',N'nvarchar(max)'),1,9,N'') + N' 
        WITH NAME = N''' + @dbname + CASE @type 
        WHEN 'bak' THEN N'_PMAGFull' ELSE N'_PMAGLog' END 
        + ''', INIT, FORMAT' + CASE WHEN LEFT(CONVERT(NVARCHAR(128), 
        SERVERPROPERTY(N'Edition')), 3) IN (N'Dev', N'Ent')
        THEN N', COMPRESSION;' ELSE N';' END;
 
  EXEC [master].sys.sp_executesql @sql;
 
  IF @type = 'bak' AND @init = 1  -- initialize log shipping
  BEGIN
    EXEC dbo.PMAG_InitializeSecondaries @dbname = @dbname, @fn = @fn;
  END
 
  IF @type = 'trn'
  BEGIN
    -- record the fact that we backed up a log
    INSERT dbo.PMAG_LogBackupHistory
    (
      DatabaseName, 
      ServerInstance, 
      BackupSetID, 
      Location
    )
    SELECT 
      DatabaseName = @dbname, 
      ServerInstance = s.ServerInstance, 
      BackupSetID = MAX(b.backup_set_id), 
      Location = s.CommonFolder + @fn
    FROM msdb.dbo.backupset AS b
    CROSS JOIN dbo.PMAG_Secondaries AS s
    WHERE b.name = @dbname + N'_PMAGLog'
      AND s.DatabaseName = @dbname
    GROUP BY s.ServerInstance, s.CommonFolder + @fn;
 
    -- once we've backed up logs, 
    -- restore them on the next secondary
    EXEC dbo.PMAG_RestoreLogs @dbname = @dbname;
  END
END
```
b. Membuat store procedure`PMAG_IntializeSecondaries` <br>
Store procedure ini berfungsi untuk inisiasi awal log shipping.
```
CREATE PROCEDURE dbo.PMAG_InitializeSecondaries
  @dbname SYSNAME,
  @fn     VARCHAR(512)
AS
BEGIN
  SET NOCOUNT ON;
 
  -- clear out existing history/settings (since this may be a re-init)
  DELETE dbo.PMAG_LogBackupHistory  WHERE DatabaseName = @dbname;
  DELETE dbo.PMAG_LogRestoreHistory WHERE DatabaseName = @dbname;
  UPDATE dbo.PMAG_Secondaries SET IsCurrentStandby = 0
    WHERE DatabaseName = @dbname;
 
  DECLARE @sql   NVARCHAR(MAX) = N'',
          @files NVARCHAR(MAX) = N'';
 
  -- need to know the logical file names - may be more than two
  SET @sql = N'SELECT @files = (SELECT N'', MOVE N'''''' + name 
    + '''''' TO N''''$'' + CASE [type] WHEN 0 THEN N''df''
      WHEN 1 THEN N''lf'' END + ''$''''''
    FROM ' + QUOTENAME(@dbname) + '.sys.database_files
    WHERE [type] IN (0,1)
    FOR XML PATH, TYPE).value(N''.[1]'',N''nvarchar(max)'');';
 
  EXEC master.sys.sp_executesql @sql,
    N'@files NVARCHAR(MAX) OUTPUT', 
    @files = @files OUTPUT;
 
  SET @sql = N'';
 
  -- restore - need physical paths of data/log files for WITH MOVE
  -- this can fail, obviously, if those path+names already exist for another db
  SELECT @sql += N'EXEC ' + QUOTENAME(ServerInstance) 
    + N'.master.sys.sp_executesql N''RESTORE DATABASE ' + QUOTENAME(@dbname) 
    + N' FROM DISK = N''''' + CommonFolder + @fn + N'''''' + N' WITH REPLACE, 
      NORECOVERY' + REPLACE(REPLACE(REPLACE(@files, N'$df$', DataFolder 
    + @dbname + N'.mdf'), N'$lf$', LogFolder + @dbname + N'.ldf'), N'''', N'''''') 
    + N';'';' + CHAR(13) + CHAR(10)
  FROM dbo.PMAG_Secondaries
  WHERE DatabaseName = @dbname;
 
  EXEC [master].sys.sp_executesql @sql;
 
  -- backup a log for this database
  EXEC dbo.PMAG_Backup @dbname = @dbname, @type = 'trn';
 
  -- restore logs
  EXEC dbo.PMAG_RestoreLogs @dbname = @dbname, @PrepareAll = 1;
END
```
c. Membuat store procedure `PMAG_RestoreLogs`<br>
Store procedure ini digunakan untuk proses restore dari backup yang dilakukan.
```
CREATE PROCEDURE dbo.PMAG_RestoreLogs
  @dbname     SYSNAME,
  @PrepareAll BIT = 0
AS
BEGIN
  SET NOCOUNT ON;
 
  DECLARE @StandbyInstance SYSNAME,
          @CurrentInstance SYSNAME,
          @BackupSetID     INT, 
          @Location        VARCHAR(512),
          @StandByLocation VARCHAR(512),
          @sql             NVARCHAR(MAX),
          @rn              INT,
          @NumOfNode       INT;
 
  -- if number of backup node is 1 than use that only one node as @StandbyInstance else, get next standby node
  SELECT @NumOfNode = COUNT(DatabaseName) from dbo.PMAG_Secondaries WHERE DatabaseName = @dbname
  
  IF @NumOfNode = 1
    SELECT @StandbyInstance = MIN(ServerInstance)
    FROM dbo.PMAG_Secondaries
    WHERE DatabaseName = @dbname
    
  ELSE
    SELECT @StandbyInstance = MIN(ServerInstance)
      FROM dbo.PMAG_Secondaries
      WHERE IsCurrentStandby = 0
        AND ServerInstance > (SELECT ServerInstance
      FROM dbo.PMAG_Secondaries
      WHERE IsCurrentStandBy = 1 AND DatabaseName = @dbname);
 
    IF @StandbyInstance IS NULL -- either it was last or a re-init
    BEGIN
      SELECT @StandbyInstance = MIN(ServerInstance)
        FROM dbo.PMAG_Secondaries;
    END
 
  -- get that instance up and into STANDBY
  -- for each log in logbackuphistory not in logrestorehistory:
  -- restore, and insert it into logrestorehistory
  -- mark the last one as STANDBY
  -- if @prepareAll is true, mark all others as NORECOVERY
  -- in this case there should be only one, but just in case
 
  DECLARE c CURSOR LOCAL FAST_FORWARD FOR 
    SELECT bh.BackupSetID, s.ServerInstance, bh.Location, s.StandbyLocation,
      rn = ROW_NUMBER() OVER (PARTITION BY s.ServerInstance ORDER BY bh.BackupSetID DESC)
    FROM dbo.PMAG_LogBackupHistory AS bh
    INNER JOIN dbo.PMAG_Secondaries AS s
    ON bh.DatabaseName = s.DatabaseName
    AND bh.ServerInstance = s.ServerInstance
    WHERE s.DatabaseName = @dbname
    AND s.ServerInstance = CASE @PrepareAll 
	WHEN 1 THEN s.ServerInstance ELSE @StandbyInstance END
    AND NOT EXISTS
    (
      SELECT 1 FROM dbo.PMAG_LogRestoreHistory AS rh
        WHERE DatabaseName = @dbname
        AND ServerInstance = s.ServerInstance
        AND BackupSetID = bh.BackupSetID
    )
    ORDER BY CASE s.ServerInstance 
      WHEN @StandbyInstance THEN 1 ELSE 2 END, bh.BackupSetID;
 
  OPEN c;
 
  FETCH c INTO @BackupSetID, @CurrentInstance, @Location, @StandbyLocation, @rn;
 
  WHILE @@FETCH_STATUS != -1
  BEGIN
    -- kick users out - set to single_user then back to multi
    SET @sql = N'EXEC ' + QUOTENAME(@CurrentInstance) + N'.[master].sys.sp_executesql '
    + 'N''IF EXISTS (SELECT 1 FROM sys.databases WHERE name = N''''' 
	+ @dbname + ''''' AND [user_access] = 0 AND [STATE] = 0)
	  BEGIN
	    ALTER DATABASE ' + QUOTENAME(@dbname) + N' SET SINGLE_USER '
      +   N'WITH ROLLBACK IMMEDIATE;
	    ALTER DATABASE ' + QUOTENAME(@dbname) + N' SET MULTI_USER;
	  END;'';';
 
    EXEC [master].sys.sp_executesql @sql;
 
    -- restore the log (in STANDBY if it's the last one):
    SET @sql = N'EXEC ' + QUOTENAME(@CurrentInstance) 
      + N'.[master].sys.sp_executesql ' + N'N''RESTORE LOG ' + QUOTENAME(@dbname) 
      + N' FROM DISK = N''''' + @Location + N''''' WITH ' + CASE WHEN @rn = 1 
        AND (@CurrentInstance = @StandbyInstance OR @PrepareAll = 1) THEN 
        N'STANDBY = N''''' + @StandbyLocation + @dbname + N'.standby''''' ELSE 
        N'NORECOVERY' END + N';'';';
 
    EXEC [master].sys.sp_executesql @sql;
 
    -- record the fact that we've restored logs
    INSERT dbo.PMAG_LogRestoreHistory
      (DatabaseName, ServerInstance, BackupSetID, RestoreTime)
    SELECT @dbname, @CurrentInstance, @BackupSetID, SYSDATETIME();
 
    -- mark the new standby
    IF @rn = 1 AND @CurrentInstance = @StandbyInstance -- this is the new STANDBY
    BEGIN
        UPDATE dbo.PMAG_Secondaries 
          SET IsCurrentStandby = CASE ServerInstance
            WHEN @StandbyInstance THEN 1 ELSE 0 END 
          WHERE DatabaseName = @dbname;
    END
 
    FETCH c INTO @BackupSetID, @CurrentInstance, @Location, @StandbyLocation, @rn;
  END
 
  CLOSE c; DEALLOCATE c;
END
```
d. Membuat store procedure `PMAG_GetActivateSecondary`<br>
Store procedure ini untuk mendapatkan daftar backup instance yang aktif
```
CREATE OR ALTER PROCEDURE dbo.PMAG_GetActiveSecondary
  @dbname SYSNAME
AS
BEGIN
  SET NOCOUNT ON;
 
  SELECT ServerInstance
    FROM dbo.PMAG_ActiveSecondaries
    WHERE DatabaseName = @dbname;
END
```
e. Membuat store procedure `PMAG_CleanupHistory`<br>
Store procedure ini digunakan untuk proses penghapusan history backup
```
CREATE OR ALTER PROCEDURE dbo.PMAG_CleanupHistory
  @dbname   SYSNAME,
  @DaysOld  INT = 7
AS
BEGIN
  SET NOCOUNT ON;
 
  DECLARE @cutoff INT;
 
  -- this assumes that a log backup either 
  -- succeeded or failed on all secondaries 
  SELECT @cutoff = MAX(BackupSetID)
    FROM dbo.PMAG_LogBackupHistory AS bh
    WHERE DatabaseName = @dbname
    AND BackupTime < DATEADD(DAY, -@DaysOld, SYSDATETIME())
    AND EXISTS
    (
      SELECT 1 
        FROM dbo.PMAG_LogRestoreHistory AS rh
        WHERE BackupSetID = bh.BackupSetID
          AND DatabaseName = @dbname
          AND ServerInstance = bh.ServerInstance
    );
 
  DELETE dbo.PMAG_LogRestoreHistory
    WHERE DatabaseName = @dbname
    AND BackupSetID <= @cutoff;
 
  DELETE dbo.PMAG_LogBackupHistory 
    WHERE DatabaseName = @dbname
    AND BackupSetID <= @cutoff;
END
```
#### 4. Pembuatan view<br>
a. Membuat view `PMAG_BackupRestoreReport` <br>
view ini digunakan untuk melihat backup yang berhasil dilakukan.
```
CREATE OR ALTER VIEW [dbo].[PMAG_BackupRestoreReport] AS SELECT
	b.BackupSetID as [ID],
	b.DatabaseName as [Database],
	b.ServerInstance as [Backup Server],
	b.BackupTime as [Backup Time],
	CONVERT(DATE, b.BackupTime) as [Backup Date],
	b.Location as [File Location],
	DATEDIFF(millisecond, b.BackupTime, r.RestoreTime) as [Duration (millisecond)]
FROM dbo.PMAG_LogBackupHistory b
	JOIN dbo.PMAG_LogRestoreHistory r ON b.BackupSetID=r.BackupSetID AND b.ServerInstance= r.ServerInstance AND b.DatabaseName= r.DatabaseName
```
b. Membuat view `PMAG_FailBackupRestoreReport` <br>
view ini digunakan untuk melihat backup yang gagal ter-restore
```
CREATE OR ALTER VIEW [dbo].[PMAG_BackupRestoreReport] AS SELECT
	b.BackupSetID as [ID],
	b.DatabaseName as [Database],
	b.ServerInstance as [Backup Server],
	b.BackupTime as [Backup Time],
	CONVERT(DATE, b.BackupTime) as [Backup Date],
	b.Location as [File Location],
	DATEDIFF(millisecond, b.BackupTime, r.RestoreTime) as [Duration (millisecond)]
FROM dbo.PMAG_LogBackupHistory b
	JOIN dbo.PMAG_LogRestoreHistory r ON b.BackupSetID=r.BackupSetID AND b.ServerInstance= r.ServerInstance AND b.DatabaseName= r.DatabaseName
```
c. Membuat view `PMAG_ActiveSecondaries`
view ini digunakan untuk melihat backup instance mana yang sedang aktif
```
CREATE OR ALTER VIEW dbo.PMAG_ActiveSecondaries
AS
  SELECT DatabaseName, ServerInstance
    FROM dbo.PMAG_Secondaries
    WHERE IsCurrentStandby = 1;
```
#### 5. Pendataan database yang akan dibackup<br>
Selanjutnya memilih database yang akan dibackup. di sini akan menggunakan database `TBD`.
```
USE TBD;
GO
INSERT dbo.PMAG_Databases(DatabaseName) SELECT N'TBD';
```
Selanjutnya memilih backup instance untuk `TBD` yaitu `VENYUTZKY\SEC1` dan `VENYUTZKY\SEC2`. Setiap instance memiliki *DataFolder* dan *LogFolder* masing-masing umumnya pada `C:\Program Files\Microsoft SQL Server\MSSQL15.{nama instance}\MSSQL\DATA\`. Untuk lokasi folder backup dan standby dari setiap backup instance adalah `D:\SEC1`dan `D:\SEC2`. <br>
```
INSERT dbo.PMAG_Secondaries
(
  DatabaseName,
  ServerInstance, 
  CommonFolder, 
  DataFolder, 
  LogFolder, 
  StandByLocation
)
SELECT 
  DatabaseName = N'TBD', 
  ServerInstance = name,
  CommonFolder = 'D:\SEC' + RIGHT(name, 1) + '\', 
  DataFolder = 'C:\Program Files\Microsoft SQL Server\MSSQL15.SEC'  
               + RIGHT(name, 1) + '\MSSQL\DATA\',
  LogFolder  = 'C:\Program Files\Microsoft SQL Server\MSSQL15.SEC' 
               + RIGHT(name, 1) + '\MSSQL\DATA\',
  StandByLocation = 'D:\SEC' + RIGHT(name, 1) + '\' 
FROM sys.servers 
WHERE name LIKE N'.\SEC[1-2]';
```
#### 6. inisiasi Backup<br>
Dilakukan inisiasi backup untuk `TBD` dengan mengeksekusi store procedure `PMAG_Backup` dengan paramater `type=bak` dan `init = 1`<br>
```
EXEC dbo.PMAG_Backup @dbname = N'TBD', @type = 'bak', @init = 1;
```
Jika berhasil, dapat menjalankan log backup store procedure yang sama dengan parameter `type=trn`
```
EXEC dbo.PMAG_Backup @dbname = N'TBD', @type = 'trn';
```

## Pembangunan Web App
Untuk web app dibuat menggunakan *Streamlit*. alasan menggunakan *streamlit* karena lebih mudah.
![image](https://user-images.githubusercontent.com/54930670/146622570-f7668139-0d2d-4c8f-9517-024f59436f4f.png)

### Tahapan Pembangunan
#### 1. Melakukan instalasi virtual environment dalam workspace folder dan menjalankannya menggunakan `terminal`
```
python.exe -m venv . 
```
kemudian mengaktifkan virtual environment dengan masuk ke dalam folder `Scripts` dan mengetikkan `activate` di dalam `terminal`. setelah virtual environment aktif maka dapat dilakukan instalasi `streamlit` dan library yang lainnya.
```
pip install streamlit
pip install pandas
pip install pyodbc
pip install datetime
pip install pymongo
```
Setelah semua proses instalasi telah dilakukan. maka streamlit dapat dijalankan pada folder `Log Shipping`.
```
streamlit run app.py
```

## Pembuatan Automasi Backup
1. buka task scheduler yang ada pada windows.
2. pada bagian `Actions` pilih `Create Task`
![image](https://user-images.githubusercontent.com/54930670/146623330-1eddcc7e-2aee-4fc8-affa-0ed3d417e255.png)
3. Kemudian masukkan nama dan lokasi dan pilih radio button sesuai dengan gambar di bawah
 <br>
![image](https://user-images.githubusercontent.com/54930670/146623430-e729f252-dcbf-41f6-b9a6-1e831f304c78.png)
<br>
4. Pada bagian `Triggers` klik bagian `New` dan pilih sesuai dengan gambar dibawah untuk dilakukan 15 menit.
![image](https://user-images.githubusercontent.com/54930670/146623676-fec9c8de-dffb-441f-a788-1f255a9b7a04.png)
<br>
5. Pada bagian `Actions` klik bagian `New` lalu inputkan script berikut ke dalam `Program/script`
```
sqlcmd -S VENYUTZKY -d TBD -E -Q "EXEC dbo.PMAG_Backup @dbname = N'TBD', @type = 'trn';"
```
<br>
![image](https://user-images.githubusercontent.com/54930670/146623533-9bdce106-bf88-4536-8c89-b3e14e8ba36c.png)
<br>
6. Pada bagian `Conditions` dan bagian `Power` uncheck *start the task only if the computer is on AC power*
<br>
![image](https://user-images.githubusercontent.com/54930670/146623601-bfde02cb-7786-4e9d-afc1-ca363d8def17.png)
<br>
7. Pada bagian `Settings` check *Run task as soon as Possible after a scheduled start is missed*
<br>
![image](https://user-images.githubusercontent.com/54930670/146623641-0b811998-d2cd-46d3-b69e-798132dba290.png)
<br>
8. Klik `OK`

