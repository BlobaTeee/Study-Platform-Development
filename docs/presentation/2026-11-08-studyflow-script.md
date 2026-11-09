# StudyFlow — script thuyết trình & demo (bản 2026-11-08)

**Thời lượng:** khoảng 16 phút nói + 4 phút hỏi đáp. Phần in *nghiêng* là phần cắt được nếu bị gấp.
Phần trong `> …` là lời nói; phần trong `[…]` là thao tác trên màn hình.

**Người nghe:** hội đồng và khán giả không nhất thiết học về AI. Mỗi khi nhắc một thuật ngữ, nói luôn
một câu đời thường đi kèm (bảng giải thích ở cuối script).

**Chuẩn bị trước khi vào phòng**

- `pnpm dev:all` đã chạy (giao diện Next + backend uvicorn), đăng nhập tài khoản demo
  `studyflow.demo@gmail.com`.
- **Mở trước một lượt mọi trang sẽ demo ở chế độ tiếng Việt.** Lần đầu mở, phần dịch mất 10–20 giây;
  từ lần thứ hai thì hiện ngay. Đừng để lần đầu rơi vào lúc đang trình bày.
- Tab notebook `ml_pipeline/notebooks/06_question_quality.ipynb` và `12_translation.ipynb` mở sẵn.
- Có sẵn một ảnh chụp đề thi (đề Toán THPT) để demo phần chụp ảnh.

**Số liệu** (lấy từ repo ngày 2026-11-09): 1.314 test tự động đang chạy đạt (53 giao diện, 677 phần ML,
584 API); khoảng 28.000 dòng code (giao diện ~12.200, backend ~13.200, ML ~2.800) và ~13.000 dòng test;
12 notebook đo đạc; 7 bộ dữ liệu công khai.

---

## 1. Mở đầu — vấn đề, 45 giây

> Khi ôn thi, việc tốn thời gian nhất thường không phải là học, mà là **biến tài liệu thành thứ để học**:
> đọc 40 trang slide, tự viết thẻ ghi nhớ, tự đặt câu hỏi. Làm xong thì hết buổi, chưa ôn được gì.
>
> Và kể cả khi đã có câu hỏi, mình vẫn không biết **mình yếu ở đâu**, hay **đến ngày thi còn nhớ được
> bao nhiêu**.
>
> StudyFlow làm hai việc đó: đưa tài liệu vào, nó tạo ra thẻ ghi nhớ, bài kiểm tra, bài vận dụng; rồi nó
> theo dõi bạn sai ở đâu để đưa bạn quay lại đúng chỗ cần học.

---

## 2. StudyFlow là gì — 1 phút

> Nói một câu: **StudyFlow là một trang web ôn thi, lấy chính tài liệu của bạn làm đề.**
>
> Một vòng học trên StudyFlow có bốn bước:
>
> 1. **Đưa tài liệu vào** — file PDF, Word, PowerPoint, dán chữ, hoặc dán link một trang web.
> 2. **Hệ thống đọc và rút ra ý chính**, rồi từ đó tạo thẻ ghi nhớ, bài kiểm tra, bài thi thử và bài vận dụng.
> 3. **Bạn học**: một mình, hoặc cùng nhóm trong thời gian thực.
> 4. **Hệ thống theo dõi** bạn nhớ gì, quên gì, hay nhầm gì, và đề xuất học gì tiếp.
>
> Mỗi môn học là một **sổ tay**; trong sổ tay là các **tài liệu** của môn đó.

[Mở trang chủ: chỉ "40 thẻ cho hôm nay", thẻ đầu tiên của hàng đợi, danh sách sổ tay với mức "Nắm chắc /
Khá ổn".]

---

## 3. Công nghệ — 2 phút

Nói bằng hình ảnh một nhà hàng; chỉ đọc tên công nghệ, không giải thích từng thư viện.

> Một trang web giống một nhà hàng.
>
> **Phòng ăn — phần bạn nhìn thấy** (frontend): viết bằng **Next.js** và **React**, ngôn ngữ
> **TypeScript**, giao diện bằng **Tailwind**. Có hai ngôn ngữ Anh–Việt; công thức toán hiển thị
> bằng **KaTeX**.
>
> **Nhà bếp — phần xử lý phía sau** (backend): **Django**, một framework của Python. Cùng một chương trình
> đó còn chạy **Socket.IO** để nhắn tin và học nhóm theo thời gian thực — tin nhắn đến ngay, không cần tải
> lại trang.
>
> **Nhà kho — nơi lưu dữ liệu**: cơ sở dữ liệu **PostgreSQL** trên **Supabase**. Đăng nhập cũng do Supabase
> lo (có cả Google, GitHub), nhưng backend **không tin lời trình duyệt**: mỗi yêu cầu mang theo một "vé" có
> chữ ký, backend tự kiểm tra chữ ký đó rồi mới cho vào.
>
> **Phần AI** có ba loại, và đây là điều tôi muốn nói rõ:
>
> - **Mô hình ngôn ngữ lớn thuê ngoài** — **Gemini** của Google. Hiểu đơn giản: một chương trình đã đọc rất
>   nhiều văn bản, nên đọc hiểu và viết được câu. Nó dùng để viết thẻ, câu hỏi, và chấm những gì cần hiểu
>   nghĩa. Nếu Gemini hết lượt hoặc quá tải, hệ thống chuyển sang model dự phòng, rồi sang **Ollama** —
>   một model nhỏ chạy ngay trên máy.
> - **Mô hình nhỏ tôi tự huấn luyện** bằng **scikit-learn**. Hiểu đơn giản: cho chương trình xem hàng nghìn
>   ví dụ có sẵn đáp án, nó tự rút ra quy luật — giống học sinh luyện nhiều đề có đáp án. Dùng để chấm câu
>   trả lời và gom các câu sai thành nhóm.
> - **Mô hình dịch chạy ngay trên máy** — **PyTorch** và **Transformers**, dùng để dịch nội dung tài liệu
>   sang ngôn ngữ của trang.
>
> Và có những phần **không phải AI** mà là công thức đã được nghiên cứu: lịch ôn thẻ, dự báo trí nhớ.
> Tôi sẽ chỉ ra từng chỗ.
>
> *Mọi thí nghiệm AI được ghi lại trong 12 notebook Jupyter, chạy lại được từ đầu, trên 7 bộ dữ liệu công
> khai: SciQ, MMLU, ASSISTments, Duolingo, ProcessBench, IWSLT và một bộ flashcard.*

---

## 4. Các tính năng — 8 phút, vừa nói vừa demo

Mỗi tính năng nói ba ý: **nó làm gì**, **bên trong hoạt động thế nào (nói đơn giản)**, **[demo]**.

### 4.1 Đưa tài liệu vào và đọc ý chính

> [Mở một sổ tay, chọn tài liệu "Energy and waves".]
>
> Khi tải file lên ở trang Sổ tay, hệ thống **tự xếp file vào đúng môn**: file hoá thì vào sổ Hoá.
>
> Sau đó nó **đọc tài liệu một lần** và rút ra danh sách **ý chính**, ý cốt lõi lên trước. Mọi thẻ và câu
> hỏi đều được viết **từ các ý chính này**, nên không hỏi những chi tiết vụn vặt như "trang 3 có bao nhiêu
> hình".
>
> [Bấm một ý chính để mở ra.] Dưới mỗi ý chính là **đoạn trích nguyên văn** trong tài liệu. Đây là điểm
> thiết kế quan trọng nhất của đồ án: **mọi thứ hệ thống tạo ra từ tài liệu đều truy được về đúng câu trong tài liệu đó**.
> Nhờ vậy, người học kiểm tra được, và tôi đo được AI có bịa hay không.
>
> *Mỗi tài liệu còn có một đoạn tóm tắt, và mỗi sổ tay có phần tổng quan cả môn.*

### 4.2 Thẻ ghi nhớ (flashcard)

> [Mở flashcard.] Mặt trước là câu hỏi, mặt sau là đáp án **ngắn** — đủ ngắn để tự nhớ ra. Phần giải thích
> dài được gấp lại, muốn đọc thì mở.
>
> Có thêm **thẻ điền từ**: một câu bị khuyết một chỗ, bạn gõ chữ còn thiếu, hệ thống so ngay.
>
> Lật thẻ xong, bạn tự chấm **Khó / Ổn / Dễ**. Bên trong là thuật toán **ôn giãn cách** tên SM-2: thẻ bạn
> nhớ rõ thì lâu sau mới hỏi lại, thẻ hay quên thì quay lại sớm. Không có AI ở đây, là một công thức.
>
> Để không bị ngợp: mỗi ngày có **giới hạn số thẻ**; khi đang nợ nhiều thẻ cũ thì **tạm dừng thẻ mới**; môn
> nào **sắp thi** thì được ưu tiên lên trước.
>
> [Lật một thẻ, mở "Vẫn chưa rõ? Hỏi thêm về thẻ này".] Sau khi lật thẻ, nếu vẫn chưa hiểu, bạn hỏi được
> **gia sư** tối đa ba câu, trả lời dựa trên đoạn tài liệu của thẻ đó. Chỉ có sau khi bạn đã thử nhớ —
> không thay cho việc tự nhớ.

### 4.3 Bài kiểm tra

> [Mở một bài kiểm tra.] Trắc nghiệm bình thường. Nhưng có chế độ **"Gõ câu trả lời"**: không có lựa chọn
> để đoán, bạn phải tự nhớ ra.
>
> Chấm câu gõ có ba lớp, từ rẻ tới đắt:
>
> 1. **Luật so khớp** — gõ đúng hoặc gần đúng chữ của đáp án, hay gõ trúng một phương án sai, thì xử lý ngay.
> 2. **Mô hình tôi tự huấn luyện** — đọc câu hỏi và đoạn tài liệu, đánh giá câu bạn gõ giống đáp án nào.
> 3. Chỉ khi mô hình **không chắc**, mới hỏi **Gemini**.
>
> Lý do: phần lớn câu được chấm trong vài mili giây, không tốn lượt AI. Và **bạn luôn có quyền nói "Tôi
> đúng"** — người học là người quyết định cuối.
>
> *Câu hỏi nào AI viết sai, bạn sửa hoặc xoá ngay trong lúc học.*

### 4.4 Bài thi thử

> [Mở trang Bài thi thử, xem lại một bài đã làm.] Bài thi thử lấy câu từ cả sổ tay, có **đồng hồ đếm
> ngược**. Làm xong mới có kết quả, giống thi thật.
>
> Khi xem lại, mỗi câu sai có: đáp án đúng, nút **"Vì sao sai?"** — AI giải thích dựa trên đoạn tài liệu —
> và **đúng đoạn tài liệu** câu hỏi được lấy ra, kèm link mở ngay chỗ đó.
>
> Câu sai vào danh sách **"Câu sai cần làm lại"**. Một câu chỉ ra khỏi danh sách khi bạn làm đúng **hai lần
> liên tiếp** — một lần đúng có thể là đoán may.
>
> *Bạn còn đặt được lịch thi thật: hệ thống gửi email nhắc trước giờ thi và ưu tiên ôn môn đó.*

### 4.5 Bài vận dụng

> [Mở trang Bài vận dụng.] Thẻ và trắc nghiệm kiểm tra **nhớ**. Bài vận dụng kiểm tra **dùng được kiến
> thức**: một tình huống mới, bạn giải từng bước.
>
> Đề có ba nguồn: **tạo từ tài liệu**, **tự gõ đề của bạn**, hoặc **chụp ảnh trang đề** — hệ thống đọc ảnh,
> tách ra từng câu, công thức toán hiển thị đúng; bạn chọn câu muốn làm và đối chiếu với ảnh.
>
> [Mở một bài, chỉ các ô "Bước 1, Bước 2".] Bạn viết lời giải theo từng bước rồi nộp. Hệ thống chấm theo
> một **đáp án ẩn** gồm lời giải mẫu, các mốc phải đạt và các lỗi hay gặp, rồi chỉ ra **bước sai đầu
> tiên** và loại lỗi. Có nút **Gợi ý** khi bí, và lời giải mẫu chỉ mở khi bạn đã làm được hoặc chủ động xem.

### 4.6 Mức nắm chắc của từng ý chính

> [Quay lại danh sách ý chính của một tài liệu.] Bên cạnh mỗi ý chính có một chấm màu: **Nắm chắc / Chưa
> vững / Yếu / Chưa học**.
>
> Mức đó tính từ hai thứ: **hiểu** — dựa trên các câu bạn làm đúng/sai về ý đó — và **nhớ** — bạn còn nhớ
> được bao lâu nữa. Lấy cái yếu hơn, vì hiểu mà không nhớ thì đến ngày thi vẫn mất điểm.
>
> Để làm được việc này, mỗi thẻ, câu hỏi và bài vận dụng được tự động **gắn vào ý chính** mà nó hỏi tới.

### 4.7 Giải thích lại (Feynman)

> Phương pháp Feynman: **giải thích lại một ý như đang dạy người khác** — giải thích được mới là hiểu.
>
> [Từ trang Tiến độ, mở một sổ tay trong "Thẻ hay quên", bấm nút giải thích ở một nhóm.] Bạn viết lời giải thích, AI trả về ba
> phần: **đúng ở đâu, thiếu gì, sai gì**, kèm đoạn tài liệu nên đọc lại.

### 4.8 Trang Tiến độ

> [Mở trang Tiến độ.] Ở đây hệ thống trả lời câu hỏi "tôi nên học gì tiếp":
>
> - **Lịch 14 ngày** — ngày nào có học, ôn bao nhiêu thẻ.
> - **Thẻ hay quên** — các thẻ bạn sai, **gom theo ý**, để ôn lại cả nhóm hoặc giải thích lại.
> - **Chỗ hay nhầm** — "Hay nhầm Axit với Bazơ": tìm từ những lần bạn chọn sai cùng một kiểu, kèm thẻ đối
>   chiếu hai ý cạnh nhau.
> - **Khái niệm yếu** — các câu sai được gom thành chủ đề, mỗi chủ đề có một bài luyện riêng.
> - **Dự báo ngày thi** — nếu dừng ôn từ hôm nay, đến ngày thi bạn còn nhớ được bao nhiêu thẻ, và nên ôn thẻ
>   nào trước. Dùng công thức trí nhớ **FSRS** — cũng là công thức của Anki, một ứng dụng flashcard nổi
>   tiếng.

### 4.9 Học nhóm

> [Mở chia sẻ sổ tay, rồi chat.] Mời bạn bè vào sổ tay bằng email. Tài liệu, thẻ, bài kiểm tra là **chung**;
> lịch ôn, điểm và câu sai của mỗi người là **riêng**. Có **chat nhóm** và **nhắn riêng**, tin đến ngay.
>
> [Mở "Học trực tiếp".] **Học trực tiếp**: cả nhóm cùng trả lời một câu trong cùng lúc, rồi cùng xem đáp án
> và tỉ lệ chọn từng phương án. Cả phòng **bỏ phiếu** để sang câu tiếp. Kết thúc, mỗi người có danh sách câu
> mình sai, và các câu đó vào luôn "Câu sai cần làm lại". Phần này không gọi AI lần nào.

### 4.10 Hai ngôn ngữ và đọc tài liệu bằng ngôn ngữ của trang — tính năng mới nhất

> [Chuyển trang sang tiếng Việt, mở một tài liệu tiếng Anh.] Giao diện có tiếng Anh và tiếng Việt. Câu chữ
> giao diện viết tay theo một **bảng thuật ngữ cố định** — mỗi ý chỉ một tên gọi — và có test chặn những từ
> dịch sát nghĩa kiểu "Shaky" cho "chưa vững".
>
> Mới nhất: **tài liệu tiếng Anh, trang tiếng Việt, thì nội dung hiện bằng tiếng Việt** — ý chính, thẻ,
> bài kiểm tra, bài thi thử, bài vận dụng, trang Tiến độ. Di chuột vào chữ đã dịch là thấy **bản gốc**.
>
> [Chỉ một lựa chọn trắc nghiệm.] Đáp án ngắn hiện kiểu **"Lực · Force"**: bản dịch kèm từ gốc. Lý do: dịch
> một chữ đứng riêng rất dễ sai — "Force" đứng một mình bị dịch thành "Buộc". Nên hệ thống dịch đáp án
> **kèm câu hỏi của nó** để máy hiểu đúng nghĩa, và vẫn để từ gốc bên cạnh cho chắc.
>
> Gõ câu trả lời bằng tiếng Việt cho câu hỏi tiếng Anh cũng được chấm đúng: hệ thống dịch câu bạn gõ sang
> ngôn ngữ của tài liệu rồi mới chấm.
>
> Việc dịch chạy bằng **một mô hình dịch trên máy**, không tốn lượt Gemini. Mỗi câu chỉ dịch một lần rồi
> lưu lại, nên lần sau hiện ngay.
>
> *Đoạn trích nguyên văn thì giữ nguyên tiếng gốc — đó là bằng chứng, không nên qua tay máy dịch. Những
> gì bạn tự viết cũng không dịch.*

---

## 5. Làm sao biết AI làm đúng — 2 phút

Đây là phần khác biệt của đồ án. Nói chậm, chỉ đọc cột "Nói đơn giản".

> Dùng AI thì dễ. Khó là **biết nó làm đúng hay sai**. Với mỗi chỗ dùng AI, tôi đo bằng dữ liệu, và
> **nói cả chỗ nó chưa tốt**.

| Phần | Đo thế nào | Kết quả | Nói đơn giản |
|---|---|---|---|
| Chất lượng câu hỏi AI viết (notebook 06) | Mỗi câu kiểm 3 điều: tài liệu có khẳng định đáp án không, có phương án nhiễu nào cũng đúng không, nhiễu có nhại đáp án không | Gemini 3.8-flash 10/10, Gemini 2.5-flash 14/15, model trên máy 13/15; câu cũ từ model trước chỉ 1/7 | Model mới viết câu hỏi tốt hơn hẳn bản cũ; ba model hiện tại gần như ngang nhau |
| Mô hình chấm câu trả lời (SciQ) | Cho câu hỏi + tài liệu, xếp hạng các đáp án | Đáp án đúng đứng đầu **93%**; so khớp chữ 82%; đoán bừa 25% | Tốt hơn hẳn cách so chữ đơn giản với đề khoa học phổ thông |
| Cùng mô hình đó, câu hỏi đại học (MMLU, notebook 11) | Như trên | Gần như đoán bừa | Nên khi không chắc, nó **nhường cho Gemini** quyết định |
| Chấm bài vận dụng từng bước (notebook 09) | Tìm bước sai đầu tiên, so với chuyên gia đánh dấu | 0,85 trên 22 bài toán (ProcessBench); 0,90 trên 72 bài làm tự soạn ở 4 môn (thang 0–1) | Bắt lỗi tốt; nhưng **bài đúng mà đi đường tắt** đôi khi bị chấm thiếu bước (luật hợp đồng: chỉ ~62% bài đúng được nhận ra) |
| Gắn thẻ/câu hỏi vào ý chính (notebook 10) | 81 mục có nhãn tay | **85%** gắn đúng ý | Đủ dùng; sai thường do hai ý dùng chung vài từ |
| Mức "hiểu" của từng ý chính (notebook 10, ASSISTments) | Dự đoán câu tiếp theo làm đúng hay sai | 0,690, so với 0,695 của cách đơn giản | **Chưa hơn** cách đơn giản "tỉ lệ làm đúng từ trước tới giờ" — tôi ghi rõ điều này |
| Dự báo trí nhớ (notebook 08, Duolingo) | Thử mô hình của Duolingo trên 12,9 triệu lượt học | Cách "đoán là nhớ hết" lại có sai số thấp nhất | Mô hình đó không hợp; tôi chọn **FSRS**, công thức đã kiểm chứng của Anki |
| Đọc ảnh đề thi | Đề Toán THPT 2025 thật, 4 trang | 24 câu, khoảng **1 lỗi đổi nghĩa** mỗi lần đọc | Luôn bắt người học đối chiếu với ảnh trước khi làm |
| Dịch (notebook 12, IWSLT) | So với bản dịch của người trên 100 câu | 35 điểm, so với 30 của mô hình còn lại; mô hình kia còn lặp chữ vô nghĩa ("cấu cấu cấu…") ở 11/30 đoạn của app | Chọn mô hình tốt hơn; vẫn còn dịch sai thuật ngữ |

> Bài học tôi rút ra nhiều nhất: **đọc từng ví dụ sai, đừng chỉ nhìn con số**. Ví dụ, tôi từng thấy phép
> chấm câu hỏi của chính tôi bắt oan: chữ "footnote" chứa chuỗi "not" nên bị coi là câu phủ định. Hay khi
> làm phần dịch, chạy thử trên gần 90 tên ý chính thật mới thấy tên viết hoa kiểu tiêu đề bị dịch sai hẳn nghĩa
> — "Nutrient Cycles" thành "Công thức tính toán" — và ký hiệu như "≤", "λ" bị máy dịch lặng lẽ xoá mất,
> "pH ≤ 7" thành "pH 7". Cả hai đã sửa, mỗi lỗi có test giữ lại.

---

## 6. Còn thiếu và cần cải thiện — 1,5 phút

Nói thẳng. Hội đồng sẽ hỏi; mình nói trước thì thành điểm cộng.

> **Phụ thuộc Gemini.** Gói miễn phí chỉ khoảng 20 lượt mỗi ngày cho mỗi model. Có dự phòng, nhưng model
> chạy trên máy viết kém hơn.
>
> **Máy dịch vẫn sai thuật ngữ.** Ví dụ "Bases" trong câu giải thích thành "Bazan" (một loại đá), "Work" thành
> "Công việc" thay vì "công". Hiện chỉ giảm tác hại bằng cách để từ gốc bên cạnh và di chuột xem bản gốc.
>
> **Lần dịch đầu chậm**, 10–20 giây cho một bài thi, và mô hình dịch chiếm khoảng 1 GB bộ nhớ. *Có lúc nó
> còn làm các yêu cầu khác phải xếp hàng chờ — tôi đã đo, tìm ra nguyên nhân và sửa.*
>
> **Mức "hiểu" chưa hơn cách đơn giản**, như bảng ở trên. Cần dữ liệu từ người dùng thật mới cải thiện được.
>
> **Chấm bài vận dụng còn yếu với lời giải đi đường tắt**, và bộ bài tự soạn ở 4 môn cần giáo viên từng môn
> kiểm lại nhãn.
>
> **Mẫu đo còn nhỏ** — 15 câu mỗi model, 22 bài toán, 72 bài làm. Đủ để chọn hướng, chưa đủ để khẳng định
> chắc chắn.
>
> **Chưa đọc được PDF dạng ảnh scan** — hệ thống báo rõ là không lấy được chữ. (Ảnh chụp đề bài thì đọc được.)
>
> **Chưa đưa lên server thật.** Email nhắc lịch thi chạy bằng một tác vụ hẹn giờ trên máy tôi, gửi qua Gmail
> cá nhân. Chat và học trực tiếp cần máy chủ giữ kết nối lâu; mô hình dịch cần máy chủ đủ RAM.
>
> *Chưa có: nhập bộ thẻ từ Anki/Quizlet, email tóm tắt "hôm nay có N thẻ cần ôn", bản cài như ứng dụng trên
> điện thoại.*

---

## 7. Tương lai — 1 phút

Chia ba mốc, nói rõ mốc nào đã có cơ sở.

> **Ngay tới đây:**
> một **bảng thuật ngữ khoa học Anh–Việt** để kiểm tra bản dịch, thuật ngữ sai thì sửa theo bảng; **dịch sẵn
> ngay khi tài liệu đọc xong** để không còn lần đầu chậm; và tăng mẫu đo lên khoảng 50 câu mỗi model.
>
> **Giữa kỳ:**
> đưa lên server thật — email qua nhà cung cấp chuyên dụng, nhắc lịch bằng tác vụ của server thay vì máy cá
> nhân; nhờ giáo viên gắn nhãn bộ bài vận dụng ngoài môn Toán; và dùng chính dữ liệu học của người dùng để
> cải thiện mức "hiểu" của từng ý chính.
>
> **Xa hơn:**
> đọc PDF scan, nhập bộ thẻ Anki/Quizlet làm điểm bắt đầu cho các tính năng AI, và bản dùng được trên điện
> thoại.

---

## 8. Kết — 20 giây

> Tóm lại: StudyFlow biến tài liệu của bạn thành thẻ, bài kiểm tra, bài thi thử và bài vận dụng; theo dõi bạn
> nhớ gì, quên gì, hay nhầm gì; và cho bạn học cùng nhau, bằng tiếng Việt hay tiếng Anh.
>
> Nhưng điều tôi tự tin nhất không phải là nó dùng AI — mà là **mọi thứ AI làm đều truy được về tài liệu, và
> tôi đo được nó đúng hay sai**. Khi phép đo của tôi sai, tôi tìm ra và sửa. Xin cảm ơn.

---

## Phòng câu hỏi khó

**"Đây có phải chỉ là vỏ bọc của Gemini?"**
> Không. Tắt Gemini thì vẫn còn model dự phòng và model trên máy. Phần quyết định **học gì tiếp** — lịch ôn,
> danh sách câu sai, gom khái niệm yếu, dự báo trí nhớ, học trực tiếp — không gọi AI lần nào. Mô hình chấm
> câu trả lời và mô hình dịch chạy ngay trên máy.

**"Làm sao biết AI không bịa?"**
> Mỗi câu hỏi giữ đoạn tài liệu sinh ra nó. Phép chấm kiểm tra tài liệu có thật sự khẳng định đáp án không;
> câu nào không thì bị gắn cờ. Khi xem lại bài, người học thấy đúng đoạn đó.

**"Sao không dùng Google Translate?"**
> Hai lý do: không tốn tiền và lượt gọi; và tôi đo được, sửa được — ví dụ giữ nguyên ký hiệu toán, công
> thức, chỗ trống của thẻ điền từ. Đổi lại, mô hình nhỏ hơn nên đôi khi dịch sai thuật ngữ; vì vậy luôn có
> bản gốc đi kèm.

**"Sao không dùng model mạnh nhất?"**
> Tôi đo thì các model "flash" chênh nhau một câu trên mười lăm, nằm trong sai số. Chi phí và độ trễ thì khác
> rõ. Vấn đề còn lại là phương án nhiễu kém chất lượng — cái đó lọc bằng luật rẻ hơn.

**"Khác gì Quizlet hay Anki?"**
> Anki có lịch ôn tốt nhưng bạn phải tự viết thẻ. Quizlet có thẻ nhưng không truy về nguồn và không biết bạn
> yếu ở đâu. StudyFlow nối hai đầu: tạo từ tài liệu thật, giữ nguồn, đo chất lượng, và dùng lỗi của chính bạn
> để chọn phần ôn tiếp theo.

**"Bảo mật và dữ liệu thế nào?"**
> Backend tự kiểm tra "vé" đăng nhập bằng khoá công khai của Supabase, không tin trình duyệt. Mỗi truy vấn chỉ
> thấy sổ tay mà bạn là chủ hoặc thành viên. Trong nhóm, lịch ôn, điểm và câu sai của mỗi người là riêng.
> Nói rõ một điều: để tạo thẻ và câu hỏi, nội dung tài liệu **có được gửi cho Gemini**. Khi đưa lên thật,
> người dùng cần được báo điều đó.

**"Kết quả 'hiểu' chưa hơn cách đơn giản, sao vẫn dùng?"**
> Vì nó cho thêm thông tin cách đơn giản không có — ước lượng cả khả năng đoán mò và sơ suất — và tôi ghi rõ
> giới hạn đó trong notebook 10. Khi có dữ liệu người dùng thật, đó là phần đầu tiên tôi sẽ huấn luyện lại.

---

## Bảng giải thích thuật ngữ (để trả lời khi bị hỏi)

| Thuật ngữ | Nói đơn giản |
|---|---|
| Mô hình ngôn ngữ lớn (Gemini) | Chương trình đã đọc rất nhiều văn bản, nên đọc hiểu và viết được câu |
| Huấn luyện mô hình | Cho chương trình xem nhiều ví dụ có sẵn đáp án để nó tự rút ra quy luật |
| Ôn giãn cách (SM-2) | Nhớ rõ thì lâu mới hỏi lại; hay quên thì hỏi lại sớm |
| FSRS | Công thức ước lượng bao lâu nữa thì bạn quên một thẻ; Anki cũng dùng |
| Ước lượng mức "hiểu" (BKT) | Từ chuỗi đúng/sai của bạn, ước lượng xác suất bạn đã thật sự hiểu, có tính cả đoán mò và sơ suất |
| Gom nhóm (clustering) | Xếp các câu sai giống nhau vào chung một nhóm để đặt tên chủ đề |
| BLEU | Điểm so bản máy dịch với bản dịch của người; càng cao càng giống |
| Điểm 0–1 khi chấm bước sai (F1) | Gộp hai việc: bắt được lỗi và không bắt oan; 1 là hoàn hảo |
| Realtime / Socket.IO | Tin nhắn và câu hỏi đến ngay, không cần tải lại trang |
| Frontend / Backend | Phần bạn nhìn thấy / phần xử lý phía sau |
| JWT | "Vé" đăng nhập có chữ ký, máy chủ kiểm tra được là thật |
