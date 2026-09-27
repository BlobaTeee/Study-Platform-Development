# StudyFlow — script thuyết trình & demo

**Thời lượng:** ~12 phút nói + 3 phút hỏi đáp. Cắt phần in *nghiêng* nếu bị gấp.
**Chuẩn bị trước khi vào phòng:** `pnpm dev:all` đã chạy (Next + uvicorn), một
notebook đã có sẵn 2–3 tài liệu, một quiz đã làm sai vài câu (để mistake bank có
dữ liệu), tab `ml_pipeline/notebooks/06_question_quality.ipynb` đã chạy sẵn.

Số liệu trong script này lấy từ repo ngày 2026-09-28: 614 test đang xanh (402
test pure/ML + 212 test API), khoảng 25.500 dòng code (frontend 8.311, backend
11.406, ml_pipeline + test 5.797).

---

## 1. Mở đầu — vấn đề, 45 giây

> Khi ôn thi, việc mất thời gian nhất không phải là học, mà là **biến tài liệu
> thành thứ để học**. Đọc slide 40 trang rồi tự viết flashcard, tự đặt câu hỏi —
> xong thì hết buổi, chưa ôn được gì.
>
> StudyFlow làm phần đó: đưa tài liệu vào, nó sinh ra flashcard và quiz, rồi
> theo dõi bạn sai ở đâu để bắt bạn học lại đúng chỗ đó.
>
> Nhưng điều tôi muốn nhấn mạnh hôm nay không phải "web sinh câu hỏi bằng AI" —
> cái đó ai cũng làm được. Điều tôi muốn nói là: **làm sao biết những câu hỏi đó
> có đúng hay không.** Đó là phần tôi đầu tư nhiều nhất.

---

## 2. Công nghệ — 2 phút

Nói theo ba tầng, đừng đọc hết tên thư viện.

> **Frontend** là Next.js 16 với React 19 và TypeScript, App Router. Tailwind v4
> cho giao diện, SWR để lấy dữ liệu, next-intl cho hai ngôn ngữ Anh–Việt, và
> socket.io-client cho chat.
>
> **Backend** là Django 5.2 với Django REST Framework, chạy trên ASGI qua
> uvicorn. Chạy ASGI vì trong cùng một process đó còn có một server Socket.IO —
> nên chat realtime dùng chung database và chung quyền đăng nhập với API, không
> phải dựng service thứ hai.
>
> **Database** là PostgreSQL trên Supabase. Đăng nhập cũng của Supabase, nhưng
> backend **không tin client**: mỗi request mang JWT, backend tự xác thực bằng
> JWKS công khai của Supabase, rồi mới tạo user tương ứng trong Django. Nên
> không có chỗ nào client tự nhận mình là ai được.
>
> **Phần AI** không phải một lời gọi API. Nó là một chuỗi ba lớp: pipeline
> extractive bằng scikit-learn và spaCy chạy hoàn toàn offline, một provider
> ngôn ngữ lớn — Gemini hoặc Ollama chạy local — và một lớp dự phòng cuối. Nếu
> Gemini hết quota hoặc quá tải thì hệ thống vẫn sinh được, chỉ là chất lượng
> thấp hơn. Tôi sẽ nói lại chỗ này ở phần điểm yếu.
>
> *Tài liệu đọc được: PDF, Word, PowerPoint, dán chữ trực tiếp, và dán link
> trang web.*

---

## 3. Hoạt động ra sao — 4 phút, vừa nói vừa demo

### 3.1 Từ tài liệu thành câu hỏi

> [bấm vào một notebook] Một notebook là một môn. Trong đó là các nguồn — đây là
> ba file tôi đã đưa vào.
>
> Khi sinh câu hỏi, hệ thống **không** đưa cả tài liệu vào một prompt. Nó cắt
> từng tài liệu thành từng đoạn và sinh trên từng đoạn. Hai lý do: prompt ngắn
> thì model nhỏ làm được, và quan trọng hơn — **mỗi câu hỏi giữ lại đúng đoạn
> nguồn đã sinh ra nó**.
>
> [mở trang Tests, xem lại một bài đã làm, chỉ vào phần nguồn dưới một câu]
> Chỗ này là điểm thiết kế quan trọng nhất của đồ án. Vì có đoạn nguồn đi kèm,
> hai việc trở thành khả thi: khi xem lại bài, sinh viên đọc được đúng câu trong
> tài liệu mà đáp án dựa vào, và **tôi có thể đo được** chất lượng câu hỏi. Không
> có nó thì "câu hỏi này đúng hay sai" là câu hỏi không thể trả lời bằng máy.
>
> *Đoạn nguồn được lưu cho mọi câu hỏi, nhưng hiện mới hiển thị ở phần xem lại
> mock test — đưa nó vào cả phần xem lại quiz thường là việc còn lại.*

### 3.2 Học và nhớ

> [mở flashcards] Flashcard dùng SM-2 — thuật toán spaced repetition. Mỗi lần tự
> chấm, khoảng cách lần ôn tới nhân với hệ số dễ; chấm "khó" thì khoảng cách reset
> về một ngày và hệ số giảm. Nên thẻ bạn nhớ rõ thì thưa dần, thẻ bạn hay quên
> quay lại liên tục.
>
> [mở quiz, chỉ mistake bank] Quiz thì khắt khe hơn. Câu nào làm sai sẽ vào **sổ
> nợ**, và chỉ ra khỏi sổ khi bạn làm đúng **hai lần liên tiếp**. Một lần đúng
> sau khi sai thì chưa tính — có thể là đoán may.
>
> [mở weak concepts] Nhưng "bạn còn nợ 12 câu" thì không hành động được. Nên các
> câu nợ được **gom thành khái niệm**: TF-IDF trên cả n-gram từ và n-gram ký tự,
> rồi clustering. Kết quả là "bạn yếu phần này", kèm một quiz luyện đúng phần
> đó. Dùng n-gram ký tự chứ không dùng model ngôn ngữ, nên nó chạy được cho cả
> tiếng Việt.
>
> *[mở analytics] Phần theo dõi: hoạt động 14 ngày, streak, và độ chính xác theo
> từng tài liệu — để biết yếu ở tài liệu nào, không chỉ yếu chung.*

### 3.3 Học cùng nhau

> [mở chia sẻ notebook, rồi chat] Một notebook mời được người khác bằng email,
> và người trong nhóm thấy tiến độ của nhau. Chat thì có nhóm và nhắn riêng, chạy
> realtime qua Socket.IO — cùng process với Django như tôi nói ở trên.

### 3.4 Đo chất lượng câu hỏi — phần tôi muốn kể nhất, 1,5 phút

> [mở notebook 06] Đây là phần tôi làm lại ba lần.
>
> Lần đầu tôi đo bằng cách đơn giản nhất: đáp án có nằm trong tài liệu không.
> Cách đó **sai cả hai chiều**. Câu hỏi dạng "điều nào KHÔNG được nêu" có đáp án
> cố tình không nằm trong tài liệu — bị chấm 0 dù đúng. Còn một câu hỏi hỏng vì
> **có phương án nhiễu cũng đúng** lại được cho là tốt, chỉ vì đáp án của nó
> trích từ tài liệu.
>
> Nên tôi viết lại: đo ba thứ — tài liệu có khẳng định đáp án không, có nhiễu nào
> cũng đúng không, nhiễu có nhại lại đáp án không — và lật ngược phép kiểm với
> câu phủ định.
>
> [chỉ bảng điểm] Kết quả trên cùng ba đoạn nguồn, cùng prompt: Gemini 3.8-flash
> 10/10, Gemini 2.5-flash 14/15, model local llama3.2:3b 13/15. Còn những câu
> **đã lưu trong quiz từ model cũ** chỉ 1/7.
>
> Và điều tôi học được nhiều nhất: [chỉ cell in câu trượt] tôi đọc từng câu bị
> gạch bằng mắt, và phát hiện **phép chấm của chính tôi bắt oan ba chỗ**. Chữ
> "footnote" chứa chuỗi "not" nên câu hỏi thường bị coi là câu phủ định. "At
> least 4 billion" bị coi là nhại lại "At least 8 billion", trong khi đó là bộ
> nhiễu bằng số hoàn toàn hợp lệ. Cả ba đã sửa, mỗi lỗi có một test giữ.
>
> Nếu tôi chỉ nhìn con số mà không đọc câu, tôi sẽ tin sai — và nếu sau này dùng
> phép chấm này để **lọc** câu hỏi, nó sẽ ném đi câu tốt.

---

## 4. Điểm mạnh — 1,5 phút

Nói bốn điểm, mỗi điểm một câu bằng chứng. Đừng nói "hệ thống rất mạnh".

> **Một — mọi câu hỏi truy được về nguồn.** Không chỉ để sinh viên tin, mà để hệ
> thống tự kiểm tra được chính nó.
>
> **Hai — quyết định bằng số đo, không bằng cảm giác.** Tôi đổi model vì bảng
> điểm, không vì tên model mới hơn. Và ba model đầu chênh nhau một câu trên mẫu
> 15 câu, nên tôi nói thẳng trong báo cáo: **cái đó nằm trong nhiễu**, thứ thật
> sự khác là tốc độ và độ sẵn sàng.
>
> **Ba — hỏng một lớp vẫn chạy.** Gemini hết quota thì có chuỗi model dự phòng;
> chuỗi đó hỏng thì còn Ollama local; không có provider nào thì còn pipeline
> extractive offline cho tài liệu tiếng Anh. Sinh viên không bao giờ thấy màn
> hình trắng vì Google quá tải.
>
> **Bốn — không phải vỏ bọc của chatbot.** SM-2, luật hai lần đúng liên tiếp,
> clustering khái niệm — những cái đó là quyết định sư phạm, không phải prompt.
>
> *Kèm theo: 614 test đang xanh; phần ML tái lập được qua sáu notebook và các file
> report; answer scorer đạt accuracy@1 0,906 trên test so với 0,819 của baseline
> so khớp chữ và 0,25 của đoán ngẫu nhiên.*

---

## 5. Điểm yếu — 1,5 phút

Nói thẳng. Hội đồng sẽ hỏi, nói trước thì thành điểm cộng.

> **Phụ thuộc bên thứ ba.** Hôm tôi đo, `gemini-3.5-flash` trả lỗi 503 cả ba
> lần vì quá tải, `3.8-flash` trượt một trong ba lần. Chuỗi dự phòng che được,
> nhưng free tier là free tier.
>
> **Model local yếu hơn thật.** llama3.2:3b được 13/15, và bộ câu cũ đã lưu chỉ
> 1/7. Nên chế độ offline là phương án chống sập, không phải chế độ ngang bằng.
>
> **Mẫu đo còn nhỏ.** 15 câu mỗi model, 3 đoạn nguồn. Đủ để chọn model, chưa đủ
> để khẳng định "100%". Và chỉ 7 câu đã lưu có đoạn nguồn kèm theo, vì tôi thêm
> phần lưu nguồn về sau — nên bức tranh "trước khi sửa" khá mỏng.
>
> **Không có OCR.** PDF scan thành ảnh thì không lấy được chữ; hệ thống chặn
> sớm và báo tài liệu quá ít chữ, nhưng vẫn là không dùng được.
>
> **Tiếng Việt bắt buộc phải có provider.** Pipeline offline dùng model spaCy
> tiếng Anh, chạy trên tiếng Việt thì nó khoét sai từ. Tôi chọn báo lỗi rõ ràng
> thay vì đưa ra thẻ sai.
>
> **Chưa deploy.** Nhắc lịch thi hiện chạy bằng một agent launchd trên máy tôi,
> mail gửi qua Gmail cá nhân. Đó là cấu hình môi trường phát triển, không phải
> production.
>
> *Và hai chỗ tôi biết còn hở: nếu model trả về JSON sai định dạng, client báo
> lỗi ngay chứ không thử model tiếp theo; và đoạn nguồn tuy lưu cho mọi câu hỏi
> nhưng chưa hiển thị ở phần xem lại quiz thường.*

---

## 6. Tương lai — 1 phút

Chia ba mốc, nói rõ cái nào đã có cơ sở để làm.

> **Ngay tới đây** — ba việc đã có đủ dữ liệu để làm:
> dùng chính phép chấm đó làm **bộ lọc trước khi lưu** — câu bị gắn cờ thì bỏ và
> sinh bù, mà không cần gọi AI thêm lần nào vì phép chấm chỉ mất vài chục
> mili-giây; bật JSON mode và cho JSON lỗi rơi xuống model kế tiếp; và nâng mẫu
> đo lên khoảng 50 câu mỗi model để con số đứng vững hơn.
>
> **Giữa kỳ** — học từ chính người dùng. Hiện tại khi sinh viên sửa một câu hỏi
> sai, hệ thống ghi lại nhưng chưa dùng; hàm retrain đã nhận tham số đó nhưng
> chưa xử lý. Đó là nguồn dữ liệu đúng chuyên môn nhất mà đồ án đang có mà chưa
> dùng. Cùng với đó là chọn đoạn nguồn thông minh hơn — hiện tại cắt đều, nên có
> đoạn toàn mục lục cũng bị đem đi sinh câu hỏi.
>
> **Xa hơn** — deploy thật: mail qua nhà cung cấp SMTP thật, bộ nhắc lịch chạy
> bằng cron/Celery thay vì launchd trên máy cá nhân; OCR cho PDF scan; và bản
> giao diện mới đang ở nhánh riêng thì trộn vào.

---

## 7. Kết — 20 giây

> Tóm lại: StudyFlow biến tài liệu thành flashcard và quiz, rồi dùng chính lỗi
> của sinh viên để quyết định ôn gì tiếp theo.
>
> Nhưng phần tôi tự tin nhất không phải là nó sinh được câu hỏi — mà là tôi **đo
> được** câu hỏi đó tốt hay không, và khi phép đo của tôi sai thì tôi tìm ra và
> sửa. Xin cảm ơn.

---

## Phòng câu hỏi khó

**"Sao không dùng GPT-4 / model mạnh nhất?"**
> Vì tôi đo thì thấy khác biệt giữa các model flash chỉ một câu trên mười lăm,
> nằm trong nhiễu. Chi phí và độ trễ thì khác biệt rõ. Với bài toán sinh câu hỏi
> từ một đoạn ngắn có sẵn đáp án trong đó, model mạnh hơn không giải quyết thêm
> vấn đề nào — vấn đề còn lại là nhiễu, và cái đó lọc bằng luật rẻ hơn.

**"Làm sao biết AI không bịa?"**
> Mỗi câu hỏi giữ đoạn nguồn. Phép chấm kiểm tra tài liệu có khẳng định đáp án
> không; câu nào không thì bị gắn cờ `answer_unsupported`. Trên bộ câu cũ, đúng
> ba câu bị gắn cờ đó.

**"Đây có phải chỉ là wrapper của Gemini?"**
> Nếu tắt Gemini thì hệ thống vẫn sinh được bằng pipeline scikit-learn/spaCy
> offline, và mọi phần quyết định *học gì tiếp theo* — SM-2, sổ nợ, gom khái
> niệm — không gọi AI lần nào.

**"Bảo mật thế nào?"**
> Backend tự xác thực JWT bằng JWKS của Supabase chứ không tin header từ client.
> Mọi truy vấn đọc đi qua danh sách notebook mà user là chủ hoặc thành viên;
> quyền sửa một thẻ là của người tạo hoặc chủ notebook. Trước đây thẻ công khai
> ai cũng sửa được — tôi phát hiện và đã bịt.

**"Đóng góp của bạn là gì, khác gì Quizlet/Anki?"**
> Anki có SM-2 nhưng bạn phải tự viết thẻ. Quizlet có thẻ nhưng không truy về
> nguồn. Phần của tôi là nối hai đầu đó lại: sinh từ tài liệu thật, giữ nguồn,
> rồi đo được chất lượng sinh ra — và dùng lỗi của người học để chọn phần ôn kế
> tiếp.
